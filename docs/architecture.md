# Architecture

The web UI calls a backend API. The API owns authentication, user ownership checks, policy ingestion, retrieval, claim workflows, approval checks, and final writes. Policy evidence is retrieved only within the authenticated user's selected policy.

Planned persistence is Postgres with pgvector plus persistent file storage. Original policy PDFs and generated packets belong in file storage; policy chunks, claims, messages, and events belong in Postgres. Agents prepare answers and drafts; backend action handlers enforce calculations, state changes, approval-version checks, and duplicate-action protection.

Langfuse traces should cover the request workflow. The `evals/` runner should call the same backend service path used by the application.

## Current implementation

The connected graph and FastAPI endpoints are implemented. The explicit local demo uses
in-memory checkpoints, run metadata, synthetic claim/policy adapters, and scripted model
responses (or optional live Nebius models). The Postgres schema, migration runner, and
database tests are included; connecting the workflow to persistent storage and production
login remains integration work.
See `backend-integration.md` and `api-contracts.md` for the current boundaries and limitations.

The read-only `/workflow/route` and `/workflow/estimate` preview endpoints coexist with
the authenticated `/agent/runs` workflow. Optional Langfuse observations cover these
previews and the real policy-retrieval adapter; local JSON logs cover the agent workflow.
Enable hosted observations with `LANGFUSE_TRACING_ENABLED=true` and Langfuse credentials.
Preview traces omit raw messages, policy text, credentials, and user/claim IDs; retrieval
records chunk IDs and counts. Tracing failures do not block requests, and shutdown flushes
pending observations. Full agent/reviewer/approval spans in Langfuse remain future work.
