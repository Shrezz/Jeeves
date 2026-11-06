# Architecture

The web UI calls a backend API. The API owns authentication, user ownership checks, policy ingestion, retrieval, claim workflows, approval checks, and final writes. Policy evidence is retrieved only within the authenticated user's selected policy.

Planned persistence is Postgres with pgvector plus persistent file storage. Original policy PDFs and generated packets belong in file storage; policy chunks, claims, messages, and events belong in Postgres. Agents prepare answers and drafts; backend action handlers enforce calculations, state changes, approval-version checks, and duplicate-action protection.

Langfuse traces should cover the request workflow. The `evals/` runner should call the same backend service path used by the application.

The current preview adds optional Langfuse observations for routing, deductible calculation, and policy retrieval. Enable them with `LANGFUSE_TRACING_ENABLED=true` and Langfuse credentials. API traces omit raw messages, policy text, credentials, and user/claim IDs; retrieval records chunk IDs and counts. The app remains usable when tracing is disabled or the SDK cannot initialize. Future claim/reviewer/approval paths need instrumentation when implemented.
