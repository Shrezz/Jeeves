"""Integration tests. Every SQL failure assertion checks the actual SQLSTATE."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.db.migrate import DEFAULT_DIRECTORY, MigrationError, migrate
from app.db.verify import verify_schema


def reject(conn, statement, params, state):
    import psycopg
    with pytest.raises(psycopg.Error) as error:
        with conn.transaction():  # savepoint, so one rejection doesn't poison the test
            conn.execute(statement, params)
    assert error.value.sqlstate == state


def test_install_replay_and_schema(database_factory):
    with database_factory() as url:
        assert migrate(url) == ["0001_enable_pgvector.sql", "0002_application_schema.sql"]
        assert migrate(url) == []
        report = verify_schema(url)
        assert report["ok"], report
        assert len(report["application_tables"]) == 6
        assert report["embedding_type"] == "vector(1536)"


def test_concurrent_migration_is_serialized(database_factory):
    with database_factory() as url:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: migrate(url), range(2)))
        assert sorted(map(len, results)) == [0, 2]
        assert verify_schema(url)["ok"]


def test_entire_failed_batch_rolls_back(database_factory, tmp_path):
    import psycopg
    (tmp_path / "0001_ok.sql").write_text("CREATE TABLE should_rollback (id integer);")
    (tmp_path / "0002_bad.sql").write_text("CREATE TABLE intentionally_broken (")
    with database_factory() as url:
        with pytest.raises(psycopg.errors.SyntaxError):
            migrate(url, tmp_path)
        with psycopg.connect(url) as conn:
            assert conn.execute("SELECT to_regclass('public.should_rollback'), to_regclass('public.schema_migrations')").fetchone() == (None, None)


def test_changed_history_refused(migrated_database, tmp_path):
    for path in DEFAULT_DIRECTORY.glob("*.sql"):
        (tmp_path / path.name).write_text(path.read_text())
    with (tmp_path / "0002_application_schema.sql").open("a") as out:
        out.write("\n-- changed after application\n")
    with pytest.raises(MigrationError, match="Checksum mismatch"):
        migrate(migrated_database, tmp_path)
    assert verify_schema(migrated_database)["ok"]


def test_legacy_ledger_not_silently_adopted(database_factory):
    import psycopg
    with database_factory() as url:
        with psycopg.connect(url) as conn:
            conn.execute("CREATE TABLE schema_migrations (filename text PRIMARY KEY)")
        with pytest.raises(MigrationError, match="Legacy migration ledger"):
            migrate(url)


def test_manual_schema_conflict_preserves_existing_data(database_factory):
    import psycopg
    with database_factory() as url:
        with psycopg.connect(url) as conn:
            conn.execute("CREATE TABLE users (id integer); INSERT INTO users VALUES (42)")
        with pytest.raises(psycopg.errors.DuplicateTable):
            migrate(url)
        with psycopg.connect(url) as conn:
            assert conn.execute("SELECT id FROM users").fetchall() == [(42,)]
            assert conn.execute("SELECT to_regclass('schema_migrations')").fetchone() == (None,)


def test_verification_detects_dropped_table(database_factory):
    import psycopg
    with database_factory() as url:
        migrate(url)
        with psycopg.connect(url) as conn:
            conn.execute("DROP TABLE messages")
        report = verify_schema(url)
        assert not report["ok"]
        assert any("messages" in issue for issue in report["issues"])


def test_committed_rows_survive_new_connection(database_factory):
    import psycopg
    with database_factory() as url:
        migrate(url)
        with psycopg.connect(url) as conn:
            conn.execute("INSERT INTO users (name,email,password_hash) VALUES ('Synthetic','resume@example.test','test-only')")
        with psycopg.connect(url) as conn:
            assert conn.execute("SELECT name FROM users WHERE email='resume@example.test'").fetchone() == ("Synthetic",)


@pytest.mark.parametrize("email", ["alice@example.test", "ALICE@Example.test"])
def test_email_uniqueness(sample, email):
    conn, _ = sample
    reject(conn, "INSERT INTO users(name,email,password_hash) VALUES ('Synthetic',%s,'test-only')", (email,), "23505")


def test_claim_policy_owner(sample):
    conn, ids = sample
    reject(conn, "INSERT INTO claims(user_id,policy_id,title) VALUES (%(u1)s,%(p2)s,'bad')", ids, "23503")


def test_message_claim_owner(sample):
    conn, ids = sample
    reject(conn, "INSERT INTO messages(user_id,conversation_id,claim_id,role,content) VALUES (%(u2)s,gen_random_uuid(),%(claim)s,'user','bad')", ids, "23503")


def test_event_actor_owner(sample):
    conn, ids = sample
    reject(conn, "INSERT INTO claim_events(claim_id,actor_user_id,event_type) VALUES (%(claim)s,%(u2)s,'bad')", ids, "23503")


def test_null_claim_and_system_actor_allowed(sample):
    conn, ids = sample
    conn.execute("INSERT INTO messages(user_id,conversation_id,role,content) VALUES (%(u1)s,gen_random_uuid(),'user','Question before claim')", ids)
    conn.execute("INSERT INTO claim_events(claim_id,event_type) VALUES (%(claim)s,'reviewer_result')", ids)


@pytest.mark.parametrize("status", ["filed", "submitted", "repair_completed"])
def test_invalid_workflow_status(sample, status):
    conn, ids = sample
    reject(conn, "UPDATE claims SET status=%s WHERE id=%s", (status, ids["claim"]), "23514")


@pytest.mark.parametrize("amount", ["-1", "NaN"])
def test_invalid_deductible(sample, amount):
    conn, ids = sample
    reject(conn, "UPDATE policies SET deductible=%s WHERE id=%s", (amount, ids["p1"]), "23514")


@pytest.mark.parametrize("statement", [
    "UPDATE policies SET version=0 WHERE id=%(p1)s",
    "UPDATE policies SET ingestion_status='done' WHERE id=%(p1)s",
    "UPDATE claims SET version=0 WHERE id=%(claim)s",
    "UPDATE claims SET approved_version=2 WHERE id=%(claim)s",
    "UPDATE claims SET status='prepared',packet_path='packet.pdf' WHERE id=%(claim)s",
    "UPDATE claims SET status='resolved_without_filing' WHERE id=%(claim)s",
    "UPDATE claims SET status='prepared',approved_version=version WHERE id=%(claim)s",
    "UPDATE claims SET package_json='{\"changed\":true}' WHERE id=%(claim)s",
    "UPDATE claims SET user_id=%(u2)s,policy_id=%(p2)s WHERE id=%(claim)s",
])
def test_invalid_state_or_revision_rejected(sample, statement):
    conn, ids = sample
    reject(conn, statement, ids, "23514")


def test_approval_edit_and_stale_reapproval(sample):
    conn, ids = sample
    conn.execute("UPDATE claims SET status='prepared',approved_version=version,packet_path='packet.pdf' WHERE id=%(claim)s", ids)
    conn.execute("UPDATE claims SET package_json='{\"changed\":true}',version=version+1,approved_version=NULL,packet_path=NULL,status='draft' WHERE id=%(claim)s", ids)
    assert conn.execute("SELECT version,approved_version,packet_path,status FROM claims WHERE id=%(claim)s", ids).fetchone() == (2, None, None, "draft")
    reject(conn, "UPDATE claims SET approved_version=1 WHERE id=%(claim)s", ids, "23514")


def test_duplicate_request_and_nullable_keys(sample):
    conn, ids = sample
    statement = "INSERT INTO claim_events(claim_id,event_type,request_key) VALUES (%(claim)s,'status_update','synthetic-key')"
    conn.execute(statement, ids)
    reject(conn, statement, ids, "23505")
    for _ in range(2):
        conn.execute("INSERT INTO claim_events(claim_id,event_type) VALUES (%(claim)s,'status_update')", ids)


def test_vector_dimension_and_owner_filtered_search(sample):
    conn, ids = sample
    reject(conn, "INSERT INTO policy_chunks(policy_id,page,content,embedding) VALUES (%(p1)s,1,'demo','[1,2,3]')", ids, "22000")
    for policy in (ids["p1"], ids["p2"]):
        conn.execute("INSERT INTO policy_chunks(policy_id,page,section,content,embedding) VALUES (%s,1,'Declarations','Synthetic only',array_fill(0.02::real,ARRAY[1536])::vector)", (policy,))
    query = """SELECT c.policy_id FROM policy_chunks c JOIN policies p ON p.id=c.policy_id
               WHERE p.user_id=%s AND c.policy_id=%s
               ORDER BY c.embedding <=> array_fill(0.02::real,ARRAY[1536])::vector LIMIT 5"""
    assert conn.execute(query, (ids["u1"], ids["p1"])).fetchall() == [(ids["p1"],)]
    assert conn.execute(query, (ids["u1"], ids["p2"])).fetchall() == []


def test_updated_at_and_generated_number(sample):
    conn, ids = sample
    before = conn.execute("SELECT updated_at FROM claims WHERE id=%(claim)s", ids).fetchone()[0]
    conn.execute("SELECT pg_sleep(0.01)")
    after, number = conn.execute("UPDATE claims SET title='New title' WHERE id=%(claim)s RETURNING updated_at,claim_number", ids).fetchone()
    assert after > before
    assert number == "CC-CLM-" + str(ids["claim"])[:8].upper()
    reject(conn, "UPDATE claims SET claim_number='manual' WHERE id=%(claim)s", ids, "428C9")
