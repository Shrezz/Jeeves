"""Run the UI migration against isolated PostgreSQL databases, never app data."""

from pathlib import Path
from uuid import uuid4

import pytest

from app.db.migrate import migrate

MIGRATIONS = Path(__file__).resolve().parents[4] / "apps/web/lib/db/migrations"


def seed_ui(url, status="Gathering evidence"):
    import psycopg

    policy, claim = uuid4(), uuid4()
    with psycopg.connect(url) as conn:
        conn.execute((MIGRATIONS / "0001_ui_baseline.sql").read_text())
        conn.execute(
            "INSERT INTO policies(id,owner_id,file_name,size,object_path,label) VALUES (%s,'user_A','demo.pdf',100,'private/demo','Demo')",
            (policy,),
        )
        conn.execute(
            "INSERT INTO claims(id,owner_id,policy_id,title,status) VALUES (%s,'user_A',%s,'Window',%s)",
            (claim, policy, status),
        )
        conn.execute(
            "INSERT INTO claim_messages(id,claim_id,content,kind,status,processing_status) VALUES (%s,%s,'User note','status_update',%s,'recorded')",
            (uuid4(), claim, status),
        )
    return policy, claim


def test_existing_ui_records_migrate_without_rekeying_and_replays_are_safe(database_factory):
    import psycopg

    with database_factory() as url:
        policy, claim = seed_ui(url)
        assert len(migrate(url, directory=MIGRATIONS)) == len(list(MIGRATIONS.glob("*.sql")))
        assert migrate(url, directory=MIGRATIONS) == []
        with psycopg.connect(url) as conn:
            assert conn.execute("SELECT id FROM users").fetchall() == [("user_A",)]
            assert conn.execute(
                "SELECT owner_id,policy_id,status FROM claims WHERE id=%s", (claim,)
            ).fetchone() == ("user_A", policy, "gathering_evidence")
            assert conn.execute("SELECT content,status FROM claim_messages").fetchone() == (
                "User note",
                "Gathering evidence",
            )
            conn.execute("INSERT INTO users(id) VALUES ('user_B')")
            with pytest.raises(psycopg.errors.ForeignKeyViolation), conn.transaction():
                conn.execute(
                    "INSERT INTO claims(id,owner_id,policy_id,title) VALUES (%s,'user_B',%s,'Other owner')",
                    (uuid4(), policy),
                )
            with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
                conn.execute("UPDATE claims SET status='repaired' WHERE id=%s", (claim,))
            with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
                conn.execute(
                    "UPDATE claims SET incident_json=jsonb_build_object('repair_status','filed_by_user') WHERE id=%s",
                    (claim,),
                )
            conn.execute(
                "UPDATE claims SET incident_json=jsonb_build_object('repair_status','completed') WHERE id=%s",
                (claim,),
            )
            conn.execute(
                "UPDATE claims SET incident_json=jsonb_build_object('repair_status','pending') WHERE id=%s",
                (claim,),
            )
            assert (
                conn.execute("SELECT status FROM claims WHERE id=%s", (claim,)).fetchone()[0]
                == "gathering_evidence"
            )


@pytest.mark.parametrize("status", ["Package prepared", "filed_demo", "resolved", "unexpected"])
def test_ambiguous_legacy_status_rolls_back_entire_migration(database_factory, status):
    import psycopg

    with database_factory() as url:
        _, claim = seed_ui(url, status)
        with pytest.raises(psycopg.errors.RaiseException):
            migrate(url, directory=MIGRATIONS)
        with psycopg.connect(url) as conn:
            assert conn.execute("SELECT status FROM claims WHERE id=%s", (claim,)).fetchone() == (
                status,
            )
            assert conn.execute(
                "SELECT to_regclass('public.users'),to_regclass('public.schema_migrations')"
            ).fetchone() == (None, None)


def test_uuid_user_schema_requires_explicit_identity_reconciliation(database_factory):
    import psycopg

    with database_factory() as url:
        seed_ui(url)
        with psycopg.connect(url) as conn:
            conn.execute("CREATE TABLE users(id uuid PRIMARY KEY)")
        with pytest.raises(psycopg.errors.RaiseException, match="identity backfill"):
            migrate(url, directory=MIGRATIONS)


def test_empty_database_bootstrap_enforces_clerk_and_outcome_contract(database_factory):
    import psycopg

    with database_factory() as url:
        migrate(url, directory=MIGRATIONS)
        with psycopg.connect(url) as conn:
            with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
                conn.execute("INSERT INTO users(id) VALUES ('not-clerk')")
            conn.execute("INSERT INTO users(id) VALUES ('user_Example')")
            claim = uuid4()
            conn.execute(
                "INSERT INTO claims(id,owner_id,title) VALUES (%s,'user_Example','Window')",
                (claim,),
            )
            assert conn.execute("SELECT status FROM claims WHERE id=%s", (claim,)).fetchone() == (
                "draft",
            )
            with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
                conn.execute("UPDATE claims SET insurer_outcome='approved' WHERE id=%s", (claim,))
            conn.execute(
                "UPDATE claims SET status='insurer_decision_received',insurer_outcome='approved',insurer_outcome_source='user_reported' WHERE id=%s",
                (claim,),
            )


def test_local_pdf_and_index_readiness_constraints(database_factory):
    import psycopg

    with database_factory() as url:
        migrate(url, directory=MIGRATIONS)
        with psycopg.connect(url) as conn:
            conn.execute("INSERT INTO users(id) VALUES ('user_Index')")
            pid = conn.execute(
                "INSERT INTO policies(owner_id,file_name,size,object_path,label) VALUES ('user_Index','test.pdf',5,'local-db:test','Test') RETURNING id"
            ).fetchone()[0]
            with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
                conn.execute("INSERT INTO policy_documents VALUES (%s,%s)", (pid, b""))
            with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
                conn.execute("UPDATE policies SET ingestion_status='ready' WHERE id=%s", (pid,))
            conn.execute("INSERT INTO policy_documents VALUES (%s,%s)", (pid, b"hello"))
            conn.execute("UPDATE policies SET ingestion_status='ready',indexed_chunks=1 WHERE id=%s", (pid,))
            assert conn.execute("SELECT content FROM policy_documents WHERE policy_id=%s", (pid,)).fetchone() == (b"hello",)
