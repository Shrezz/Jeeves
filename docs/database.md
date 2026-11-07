# Database setup and verification

> Historical prototype schema. The shared application now extends the UI schema
> using Clerk IDs. Follow [shared identity and status](identity-status-mapping.md)
> for its migration directory and commands. Do not apply the prototype commands
> below to the UI database. The verifier below checks only the prototype schema.

This database-only increment implements the six-table contract in section 9 of
`SV-InsuranceAgent-requirements.pdf` v0.2. It does not integrate authentication,
API persistence, agents, a live embedding model, or the browser UI.

## Files and schema contract

- `apps/api/migrations/0001_enable_pgvector.sql`: existing extension migration, unchanged.
- `apps/api/migrations/0002_application_schema.sql`: users, policies, policy_chunks,
  claims, messages, claim_events, foreign keys, indexes, and revision guard.
- `apps/api/app/db/migrate.py`: forward-only transactional migration runner.
- `apps/api/app/db/verify.py`: read-only catalog/history verifier.
- `apps/api/tests/database/`: offline and real PostgreSQL tests plus restart probe.
- `.github/workflows/database.yml`: disposable PostgreSQL 16/pgvector CI database.

`schema_migrations` is a seventh, technical bookkeeping table (not another
application entity). It records filenames, SHA-256 checksums, and application times.
The runner uses a transaction-scoped advisory lock and rolls back the entire pending
batch on failure. Missing/empty directories, duplicate migration numbers, changed
applied files, missing history files, and out-of-order history are errors, not success.
Checksums use LF-normalized UTF-8 so Windows checkouts do not cause false drift.

The prototype migration directory is `apps/api/migrations/`, NOT the older overlay's
`apps/api/db/migrations/`. Paths are resolved from the module, not the working directory.
Do not apply both migration trees. An already-applied overlay schema or a legacy ledger
without checksums needs explicit reconciliation: this runner refuses to adopt or drop it.

## Start locally (existing Docker Compose service)

From the repository root, configure `.env` with your local database user/password,
then start only the database:

```sh
docker compose up -d db
cd apps/api
python -m pip install -r requirements-db.txt
```

Set `DATABASE_URL` explicitly to the same database/user/password/port used by Compose.
The CLI does not automatically read `.env`. Example for the unmodified local-only
Compose defaults (replace them for any non-local use):

```sh
export DATABASE_URL='postgresql://claim_app:change-me-for-local-development@localhost:5432/claim_companion'
python -m app.db.migrate
python -m app.db.verify
python -m app.db.migrate
```

PowerShell uses this assignment instead of `export`:

```powershell
$env:DATABASE_URL = 'postgresql://claim_app:change-me-for-local-development@localhost:5432/claim_companion'
```

The first run should record `0001_enable_pgvector.sql` and
`0002_application_schema.sql`. Verification must return `"ok": true`, six application
tables, and `"embedding_type": "vector(1536)"`. A second migration run should report
no pending files. **A successful migration message alone is not a schema health check.**

The migration role needs schema/DDL permissions and permission to install pgvector.
Use a separate least-privileged runtime role when integrating the API. No credentials
are included in the code or printed by these commands.

The existing Compose named volume preserves Postgres data. Do not run
`docker compose down -v` against a database whose data you need. This change does not
run migrations against your machine or any deployed database automatically.

## Database protections and application responsibilities

Composite foreign keys reject claims referencing another user's policy, messages
referencing another user's claim, and human events attributed to another claim's
owner. A NULL actor is allowed for system events. Email uniqueness is case-insensitive.
Positive versions/pages, allowed statuses, finite nonnegative deductibles, JSON objects,
current-version approvals, and prepared-packet prerequisites are checked in PostgreSQL.

Once a package exists, material writes must advance version by exactly one, clear
`approved_version` and `packet_path`, and return to `draft`. The guard conservatively
treats any package/assessment/fact change as material. Keep review comments in events.
Approval actor/time/comments and the approved-version update must still be written
atomically by the future authenticated API. A CHECK constraint cannot prove that a
human approved anything, or that a referenced packet file actually exists.

Request keys are globally unique when non-NULL; application callers should store
`<claim_id>:<request_key>`. Events are intended as append-only application history;
this increment does not install runtime-role grants to enforce append-only access.

**These foreign keys are not row-level security.** The future API must authenticate
and owner-scope every read/write, including joins through policies for vector retrieval.
Never expose the migration role or unrestricted SQL to a browser or model.

`vector(1536)` is fixed in the migration. No actual embedding provider has been chosen
or connected here. Use a matching model/dimension, or introduce a new migration and
re-embed before changing that contract. Existing RAG code has not been wired to this DB.
`claim_number` is an eight-character display label derived from the UUID, not an identity
or authorization key; claim insertion should retry a rare generated-label collision.

## Tests

Offline checks (do not prove SQL execution):

```sh
cd apps/api
PYTHONPATH=. python -m pytest -q tests/database/test_migrations.py
```

Real tests require `TEST_DATABASE_URL` for a **disposable** database whose name ends in
`_test`, with a role allowed to create/drop temporary test databases. They never fall
back to `DATABASE_URL`, and never truncate application tables. Example using local
Compose defaults (run the first command from the repository root):

```sh
docker compose exec db createdb -U claim_app claim_companion_test
cd apps/api
export TEST_DATABASE_URL='postgresql://claim_app:change-me-for-local-development@localhost:5432/claim_companion_test'
REQUIRE_DATABASE_TESTS=1 PYTHONPATH=. python -m pytest -q tests/database
```

On PowerShell, set `$env:TEST_DATABASE_URL`, `$env:REQUIRE_DATABASE_TESTS = '1'`, and
`$env:PYTHONPATH = '.'`, then run `python -m pytest -q tests/database`.
Missing DB configuration is a skip locally and a failure with REQUIRE_DATABASE_TESTS=1.
CI always sets that flag. Failure assertions check SQLSTATE, so unrelated SQL errors
cannot make a constraint test look successful. CI also restarts its test container and
checks that the schema, migration ledger, extension, and a committed synthetic row survive.

## Verification record at commit preparation

- Local offline run: **17 passed**.
- Full local collection: **17 passed, 32 skipped**; no PostgreSQL server/driver in the sandbox.
- Real DB tests, rollback/concurrency, and container-restart checks: use the GitHub Actions
  result for the exact commit. Do not treat this document as a claim that they have passed.
- No application/deployed database has been migrated by this change.
