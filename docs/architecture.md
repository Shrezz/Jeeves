# Architecture

The web UI calls a backend API. The API owns authentication, user ownership checks, policy ingestion, retrieval, claim workflows, approval checks, and final writes. Policy evidence is retrieved only within the authenticated user's selected policy.

Planned persistence is Postgres with pgvector plus persistent file storage. Original policy PDFs and generated packets belong in file storage; policy chunks, claims, messages, and events belong in Postgres. Agents prepare answers and drafts; backend action handlers enforce calculations, state changes, approval-version checks, and duplicate-action protection.

Optional Langfuse tracing covers workflow runs, graph nodes, RAG ingestion and retrieval, and Nebius model calls. Workflow start and resume traces share an opaque run ID as a Langfuse session. Traces capture safe route, review outcome, issue codes, revision count, human action, chunk IDs, timing, and available provider token usage. Cost appears only if provider/model pricing is available in Langfuse; it is never estimated by the application.

## Current implementation

The connected graph and FastAPI endpoints are implemented. The explicit local demo uses
in-memory checkpoints, run metadata, synthetic claim/policy adapters, and scripted model
responses (or optional live Nebius models). Production Postgres persistence and login remain
external integration work. Local JSON tracing remains the fallback when Langfuse is disabled.
See `backend-integration.md` and `api-contracts.md` for the current boundaries and limitations.

The read-only `/workflow/route` and `/workflow/estimate` preview endpoints remain available alongside the agent API; they do not access or modify claims.

Set `LANGFUSE_TRACING_ENABLED=true` and the Langfuse keys and base URL to enable export. By default traces omit raw messages, prompts, policy text, and reviewer details. `LANGFUSE_CAPTURE_SYNTHETIC_CONTENT=true` additionally records redacted model inputs/outputs, evidence excerpts, and reviewer feedback only when `JEEVES_MODE=demo`. That opt-in is exclusively for fictional data: never enter credentials, session tokens, or real policyholder data into demo inputs. Redaction is best effort, not a substitute for synthetic data. The app continues working if tracing is disabled or cannot initialize.
