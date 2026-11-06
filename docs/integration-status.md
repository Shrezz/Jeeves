# Claim Companion integration status

Requirements baseline: `SV-InsuranceAgent-requirements.pdf`, v0.2, November 5, 2026.

## Implemented in this branch

- Conservative three-intent routing: `answer_claim`, `file_claim`, `save_claim_status`.
- Short clarification for ambiguous requests and missing claim selection on status updates.
- Code-owned, nonnegative, decimal-safe deductible estimate.
- Read-only `POST /workflow/route` and `POST /workflow/estimate` preview endpoints.
- Unit and API contract tests.

These are foundational utilities, **not** an end-to-end integrated app. They do not authenticate
users, retrieve policies, create claim records, approve claims, generate packets or file claims.
Do not attach the route endpoint directly to a final action.

## Existing foundation retained

The repository already contains page-aware policy extraction/chunking, a retrieval interface,
and a PostgreSQL/pgvector Docker service. The embeddings provider and persistent chunk store
are interfaces only and still need implementations.

## Outstanding for R1–R14

1. Build auth, expiring HttpOnly sessions, owner-scoped six-table database and migrations.
2. Implement text-PDF policy uploads, embeddings, pgvector store and citation-aware Q&A.
3. Implement claim drafting, read-only reviewer, at most one refinement, missing facts.
4. Implement human review with version-bound approval and guarded PDF export.
5. Implement UI dashboard, chat/history, status-event confirmation and persistent files.
6. Implement the 12-case golden evaluation, traces and measured report.

## Verify locally

```sh
cd apps/api
python -m pip install -e '.[test]'
pytest -q
uvicorn app.main:app --reload
```

The tests were authored but **not executed** in this GitHub connector session.
