"""Read-only live-schema verification. Run: python -m app.db.verify"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

from .migrate import DEFAULT_DIRECTORY, MigrationError, connect_database, load_migrations, pending_migrations

# These are the DB contract, not a substitute for the behavioral PostgreSQL tests.
COLUMNS = {
    "users": "id name email password_hash created_at",
    "policies": "id user_id label file_path version deductible metadata_json ingestion_status created_at updated_at",
    "policy_chunks": "id policy_id page section content embedding created_at",
    "claims": "id claim_number user_id policy_id title incident_json assessment_json package_json status version approved_version packet_path created_at updated_at",
    "messages": "id seq user_id conversation_id claim_id role content attachment_path created_at",
    "claim_events": "id seq claim_id actor_user_id event_type details_json request_key created_at",
    "schema_migrations": "filename checksum applied_at",
}
CONSTRAINTS = {
    "policies": {"policies_ingestion_status_check", "policies_deductible_check", "policies_id_user_key", "policies_user_version_key"},
    "claims": {"claims_status_check", "claims_approval_version_check", "claims_final_approval_check", "claims_prepared_packet_check", "claims_packet_approval_check", "claims_policy_owner_fk", "claims_id_user_key"},
    "messages": {"messages_claim_owner_fk"},
    "claim_events": {"events_claim_owner_fk", "claim_events_request_key_key"},
}
INDEXES = {
    "users_email_lower_key", "idx_chunks_policy", "idx_claims_user_updated", "idx_claims_policy",
    "idx_messages_conversation", "idx_messages_claim", "idx_events_claim",
}
TRIGGERS = {("policies", "trg_policies_updated"), ("claims", "trg_claims_updated"), ("claims", "trg_claims_revision")}


def verify_schema(url: str | None = None, directory: str | Path = DEFAULT_DIRECTORY,
                  *, connector: Callable[..., Any] | None = None) -> dict[str, Any]:
    migrations = load_migrations(directory)
    url = url or os.environ.get("DATABASE_URL")
    if not url:
        raise MigrationError("DATABASE_URL is required")
    issues: list[str] = []
    connect = connector or connect_database
    with connect(url, autocommit=True, connect_timeout=10) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute("SET LOCAL search_path TO public")
            conn.execute("SET LOCAL statement_timeout = '30s'")
            version = conn.execute("SHOW server_version").fetchone()[0]
            extension = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()
            if not extension:
                issues.append("pgvector extension is missing")
            rows = conn.execute("""
                SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod)
                FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_attribute a ON a.attrelid = c.oid
                WHERE n.nspname = 'public' AND c.relkind = 'r'
                  AND a.attnum > 0 AND NOT a.attisdropped
            """).fetchall()
            columns = {(table, column): typ for table, column, typ in rows}
            for table, required in COLUMNS.items():
                for column in required.split():
                    if (table, column) not in columns:
                        issues.append(f"Missing column: public.{table}.{column}")
            expected_types = {
                ("policy_chunks", "embedding"): "vector(1536)",
                ("policies", "deductible"): "numeric(12,2)",
                ("claims", "version"): "integer",
                ("claims", "approved_version"): "integer",
            }
            for table in COLUMNS:
                if table != "schema_migrations":
                    expected_types[table, "id"] = "uuid"
            for key, expected in expected_types.items():
                if columns.get(key) != expected:
                    issues.append(f"Wrong type: {'.'.join(key)} must be {expected}")
            constraints = {(table, name) for table, name in conn.execute("""
                SELECT r.relname, c.conname FROM pg_constraint c
                JOIN pg_class r ON r.oid = c.conrelid JOIN pg_namespace n ON n.oid = r.relnamespace
                WHERE n.nspname = 'public' AND c.convalidated
            """).fetchall()}
            for table, names in CONSTRAINTS.items():
                for name in names:
                    if (table, name) not in constraints:
                        issues.append(f"Missing/unvalidated constraint: {table}.{name}")
            for table in COLUMNS:
                if (table, f"{table}_pkey") not in constraints:
                    issues.append(f"Missing primary key: {table}")
            indexes = {row[0] for row in conn.execute("""
                SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND i.indisvalid AND i.indisready
            """).fetchall()}
            issues.extend(f"Missing/invalid index: {name}" for name in sorted(INDEXES - indexes))
            triggers = set(conn.execute("""
                SELECT c.relname, t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND NOT t.tgisinternal AND t.tgenabled IN ('O', 'A')
            """).fetchall())
            issues.extend(f"Missing/disabled trigger: {table}.{name}" for table, name in sorted(TRIGGERS - triggers))
            applied = {}
            if all(("schema_migrations", name) in columns for name in ("filename", "checksum")):
                applied = dict(conn.execute("SELECT filename, checksum FROM public.schema_migrations").fetchall())
                try:
                    pending = pending_migrations(migrations, applied)
                    issues.extend(f"Pending migration: {item.filename}" for item in pending)
                except MigrationError as exc:
                    issues.append(str(exc))
            else:
                issues.append("Migration history is missing or incompatible")
    return {"ok": not issues, "server_version": version, "pgvector_version": extension[0] if extension else None,
            "embedding_type": columns.get(("policy_chunks", "embedding")),
            "application_tables": sorted(table for table in COLUMNS if table != "schema_migrations" and (table, "id") in columns),
            "applied_migrations": sorted(applied), "issues": issues}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    args = parser.parse_args()
    try:
        report = verify_schema(directory=args.directory)
    except MigrationError as exc:
        print(f"Verification refused: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Verification failed ({type(exc).__name__}, SQLSTATE={getattr(exc, 'sqlstate', 'n/a')})", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
