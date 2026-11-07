"""Forward-only SQL migrations with checksums, an advisory lock, and atomic rollback.

Run from apps/api: python -m app.db.migrate
DATABASE_URL must be explicitly set. No credentials are logged.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

DEFAULT_DIRECTORY = Path(__file__).resolve().parents[2] / "migrations"
LOCK_ID = 739124806102  # Stable application-specific transaction advisory lock.


class MigrationError(RuntimeError):
    """Unsafe configuration, missing history, or a changed applied migration."""


@dataclass(frozen=True)
class Migration:
    filename: str
    content: str
    checksum: str


# Each branch shipped an independent 0007 before integration. Keep the original
# filenames and checksums: existing databases may already have either one.
_UI_0007 = {"0007_dashboard_policy_evidence.sql", "0007_pending_repair_status.sql"}


def load_migrations(directory: str | Path = DEFAULT_DIRECTORY) -> list[Migration]:
    directory = Path(directory)
    if not directory.is_dir():
        raise MigrationError(f"Migration directory does not exist: {directory}")
    paths = sorted(directory.glob("*.sql"))
    if not paths:
        raise MigrationError(f"No SQL migrations found in {directory}; refusing a false success")
    result: list[Migration] = []
    versions: dict[str, str] = {}
    for path in paths:
        match = re.fullmatch(r"(\d{4})_[a-z0-9_]+\.sql", path.name)
        if not match or (match[1] in versions and {path.name, versions[match[1]]} != _UI_0007):
            raise MigrationError(f"Invalid or duplicate migration number: {path.name}")
        versions[match[1]] = path.name
        # Canonical LF makes checksums stable on Windows and Unix checkouts.
        content = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        if not content.strip():
            raise MigrationError(f"Empty migration: {path.name}")
        result.append(Migration(path.name, content, hashlib.sha256(content.encode()).hexdigest()))
    return result


def pending_migrations(migrations: Sequence[Migration], applied: Mapping[str, str]) -> list[Migration]:
    names = [migration.filename for migration in migrations]
    unknown = set(applied) - set(names)
    if unknown:
        raise MigrationError("Applied migration missing from checkout: " + ", ".join(sorted(unknown)))
    # These two unrelated migrations commute. Only their relative order may differ.
    if _UI_0007 <= set(names):
        pair_start = names.index(min(_UI_0007))
        names[pair_start:pair_start+2] = sorted(_UI_0007, key=lambda name: (name not in applied, name))
    if set(applied) != set(names[:len(applied)]):
        raise MigrationError("Migration history is not a contiguous prefix; refusing out-of-order apply")
    for migration in migrations:
        if migration.filename in applied and applied[migration.filename] != migration.checksum:
            raise MigrationError(f"Checksum mismatch for {migration.filename}; add a new migration instead")
    return [migration for migration in migrations if migration.filename not in applied]


def connect_database(url: str, **kwargs: Any) -> Any:
    try:
        import psycopg
    except ImportError as exc:
        raise MigrationError("Install the database dependencies: pip install -r requirements-db.txt") from exc
    return psycopg.connect(url, **kwargs)


def migrate(url: str | None = None, directory: str | Path = DEFAULT_DIRECTORY,
            *, connector: Callable[..., Any] | None = None) -> list[str]:
    migrations = load_migrations(directory)  # Validate even when there is no driver/server.
    url = url or os.environ.get("DATABASE_URL")
    if not url:
        raise MigrationError("DATABASE_URL is required; refusing to guess a target database")
    connect = connector or connect_database
    applied_now: list[str] = []
    with connect(url, autocommit=True, connect_timeout=10) as conn:
        with conn.transaction():
            conn.execute("SET LOCAL search_path TO public")
            conn.execute("SET LOCAL lock_timeout = '15s'")
            conn.execute("SET LOCAL statement_timeout = '120s'")
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS public.schema_migrations (
                    filename text PRIMARY KEY,
                    checksum text NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
                    applied_at timestamptz NOT NULL DEFAULT now()
                )
            """)
            columns = {row[0] for row in conn.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'schema_migrations'
            """).fetchall()}
            if not {"filename", "checksum", "applied_at"}.issubset(columns):
                raise MigrationError("Legacy migration ledger detected; reconcile it before applying, do not delete data")
            applied = dict(conn.execute(
                "SELECT filename, checksum FROM public.schema_migrations ORDER BY filename"
            ).fetchall())
            for migration in pending_migrations(migrations, applied):
                conn.execute(migration.content, prepare=False)
                conn.execute(
                    "INSERT INTO public.schema_migrations (filename, checksum) VALUES (%s, %s)",
                    (migration.filename, migration.checksum),
                )
                applied_now.append(migration.filename)
    return applied_now


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    args = parser.parse_args()
    try:
        names = migrate(directory=args.directory)
    except MigrationError as exc:
        print(f"Migration refused: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        # Driver messages may include a DSN. Only expose the type and safe SQLSTATE.
        print(f"Migration failed ({type(exc).__name__}, SQLSTATE={getattr(exc, 'sqlstate', 'n/a')}); "
              "no pending migrations were committed. Check database access/schema conflicts.", file=sys.stderr)
        return 1
    print("Applied: " + ", ".join(names) if names else "No pending migrations; stored checksums match.")
    if args.directory.resolve() == DEFAULT_DIRECTORY.resolve():
        print("Next validate the prototype schema: python -m app.db.verify")
    else:
        print("Use the checks for the selected schema; app.db.verify only supports the prototype schema.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
