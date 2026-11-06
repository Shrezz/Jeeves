"""Real PostgreSQL tests create and drop isolated databases, never application data.

TEST_DATABASE_URL must name a disposable database ending in _test. Its role must
have CREATEDB permission. REQUIRE_DATABASE_TESTS=1 converts missing setup to failure.
"""
import os
from contextlib import contextmanager
from uuid import uuid4

import pytest

from app.db.migrate import migrate


@pytest.fixture(scope="session")
def database_factory():
    url = os.environ.get("TEST_DATABASE_URL")
    required = os.environ.get("REQUIRE_DATABASE_TESTS") == "1"
    if not url:
        if required:
            pytest.fail("TEST_DATABASE_URL is required in this run")
        pytest.skip("PostgreSQL test target not configured; not a database test pass")
    try:
        import psycopg
        from psycopg.conninfo import conninfo_to_dict, make_conninfo
    except ImportError:
        if required:
            pytest.fail("Database test driver is missing")
        pytest.skip("psycopg is not installed")
    params = conninfo_to_dict(url)
    if not params.get("dbname", "").endswith("_test"):
        pytest.fail("Safety check: TEST_DATABASE_URL database must end in _test")

    @contextmanager
    def factory():
        name = f"cc_{uuid4().hex}_test"
        with psycopg.connect(url, autocommit=True) as admin:
            admin.execute(psycopg.sql.SQL("CREATE DATABASE {}").format(psycopg.sql.Identifier(name)))
        try:
            yield make_conninfo(url, dbname=name)
        finally:
            with psycopg.connect(url, autocommit=True) as admin:
                admin.execute(psycopg.sql.SQL("DROP DATABASE {} WITH (FORCE)").format(psycopg.sql.Identifier(name)))
    return factory


@pytest.fixture(scope="module")
def migrated_database(database_factory):
    with database_factory() as url:
        migrate(url)
        yield url


@pytest.fixture
def sample(migrated_database):
    import psycopg
    with psycopg.connect(migrated_database) as conn:
        u1, u2, p1, p2, claim = (uuid4() for _ in range(5))
        for user, policy, email in [(u1, p1, "alice@example.test"), (u2, p2, "bob@example.test")]:
            conn.execute("INSERT INTO users (id,name,email,password_hash) VALUES (%s,'Synthetic',%s,'test-only-not-a-login')", (user, email))
            conn.execute("INSERT INTO policies (id,user_id,label,file_path,deductible,ingestion_status) VALUES (%s,%s,'Synthetic policy','demo.pdf',1000,'ready')", (policy, user))
        conn.execute("INSERT INTO claims (id,user_id,policy_id,title,package_json) VALUES (%s,%s,%s,'Synthetic window','{\"synthetic\":true}')", (claim, u1, p1))
        try:
            yield conn, {"u1": u1, "u2": u2, "p1": p1, "p2": p2, "claim": claim}
        finally:
            conn.rollback()
