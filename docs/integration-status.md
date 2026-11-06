# Claim Companion integration status

Requirements baseline: `SV-InsuranceAgent-requirements.pdf`, v0.2, November 5, 2026.

This branch combines the read-only `/workflow/route` and `/workflow/estimate` previews, the six-table Postgres schema and migration tooling, and the separately developed agent graph and API. The agent demo runs against synthetic in-memory policy, claim, artifact, and checkpoint adapters. Optional Langfuse tracing covers the graph, retrieval and configured model calls; the evaluation suite records synthetic fixture results in `evals/results/`.

The schema is not yet connected to the agent's claim, policy, checkpoint, or final-action adapters. A committed schema does not mean a database has been migrated. The broader uploaded integration overlay is separate from the independently developed agent graph; see `uploaded-backend-integration.md` and `backend-integration.md`.

Remaining work includes real authentication and sessions; owner-scoped Postgres/pgvector and file-storage adapters; durable run/checkpoint state; uploaded-policy ingestion; a downloadable PDF packet; and the web UI. The fixture results expose the in-memory restart limitation and unscored storage isolation. Synthetic Langfuse experiments have been exported and verified; human evidence review and live-model evaluation are still needed. No insurer filing is performed.

`RAG/policy_rag/` is a separately developed Chroma/OpenAI implementation. It is not wired into the agent API and differs from the requirements' Postgres/pgvector design. Its referenced test PDFs, answer key, and interactive script are not present in the checkout. The team must choose the storage integration and supply the relevant synthetic fixtures and credentials before an end-to-end RAG evaluation is possible.

Database tests require a disposable PostgreSQL server with pgvector and a `TEST_DATABASE_URL` whose database name ends in `_test`; see `database.md`. A skipped database test is not a database test pass.
