# Uploaded Claim Companion system — integration mapping

The user-supplied `claim-companion(1).zip` was inspected alongside the November 5,
2026 Claim Companion MVP design. It contains a substantive FastAPI / PostgreSQL backend
with six database tables, policy ingestion, CRUD, human approval, packet export and tests,
but **does not include a web frontend**.

## Integration overlay

A 78-file overlay was prepared for the Jeeves checkout, with these mappings:

- Uploaded `backend/app/**` -> `apps/api/app/**`
- Uploaded `backend/tests/**` -> `apps/api/tests/**`
- Uploaded `db/migrations/**` -> `apps/api/db/migrations/**`
- Uploaded `docs/API_DESIGN.md` -> `docs/API_DESIGN.md`
- New browser UI -> `apps/web/index.html`
- Adapted configuration, dependency declaration and same-origin static UI mount

Preserves the repository's existing `apps/api/app/services/rag/**` code. The
uploaded backend currently uses its **own** RAG pipeline; these implementations
are **not unified yet**.

**Important:** this note documents an integration overlay assembled outside the
GitHub repository. It does **not** mean the 78 overlay files have been committed
to GitHub. The PR currently contains only the workflow-preview foundation and
documentation. Do not merge as a completed MVP.

## Verification to date

- Python AST compilation and browser JavaScript syntax passed for the prepared overlay.
- Deterministic deductible checks passed for $150/$1,000 -> $0;
  $1,400/$1,000 -> $400; $2,500/$1,000 -> $1,500.
- PostgreSQL-backed tests were **not run** in the available sandbox
  (psycopg and a running PostgreSQL instance were unavailable).
- Agents, reviewer and embeddings are explicit deterministic stubs; Langfuse and
  LangSmith integrations remain unfinished. No insurer filing is performed.
