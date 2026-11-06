# Claim Companion integration status

Requirements baseline: `SV-InsuranceAgent-requirements.pdf`, v0.2, November 5, 2026.

## Included on this branch

The earlier conservative router, deterministic estimate, read-only workflow preview
endpoints, and their authored tests are preserved.

The database-only increment adds the six application tables, pgvector schema contract,
owner-linked foreign keys, approval/version constraints, a transactional checksum-tracked
migration runner, read-only verification, and automated database tests. See
[database.md](database.md) for setup, safety boundaries, and test evidence.

Local DB-tooling checks: **17 passed**. PostgreSQL-dependent tests: **32 skipped** locally
because a server/driver was unavailable. The GitHub Actions result for the exact commit
is the source of truth for real DB tests and the container-restart probe.

**Committed schema files do not mean a deployed database has been migrated.** No local
or deployed user database was changed in this work. API data routes have not yet been
connected to these tables. The broader uploaded integration overlay is still not merged.
The reviewed LangGraph workflow is now included through the agent branch, using synthetic
in-memory adapters.

## Still outstanding

1. Authentication, sessions, owner-scoped API persistence, and transactional approval events.
2. Policy uploads, a real embedding provider, database-backed retrieval and cited answers.
3. Connect the implemented drafting, reviewer/refinement, human-review, and export flow
   to production claims, artifact storage, and durable run/checkpoint records.
4. UI dashboard, chat/history, confirmed status updates, and persistent uploaded files.
5. Golden evaluation, traces, measured end-to-end report, and full browser validation.

The synthetic agent demo runs end to end; production integrations remain incomplete. Existing
page-aware RAG interfaces and the Compose database volume are retained unchanged.
