# Architecture

The web UI calls a backend API. The API owns authentication, user ownership checks, policy ingestion, retrieval, claim workflows, approval checks, and final writes. Policy evidence is retrieved only within the authenticated user's selected policy.

Planned persistence is Postgres with pgvector plus persistent file storage. Original policy PDFs and generated packets belong in file storage; policy chunks, claims, messages, and events belong in Postgres. Agents prepare answers and drafts; backend action handlers enforce calculations, state changes, approval-version checks, and duplicate-action protection.

Langfuse traces should cover the request workflow. The `evals/` runner should call the same backend service path used by the application.

The current preview adds optional Langfuse observations for routing, deductible calculation, PDF extraction, chunking, embedding, chunk storage, and policy retrieval. Enable them with `LANGFUSE_TRACING_ENABLED=true` and Langfuse credentials. API traces omit raw messages, policy text, credentials, and user/claim IDs; retrieval records chunk IDs and counts. The app remains usable when tracing is disabled or the SDK cannot initialize. Claim/reviewer/approval/action paths and real model usage and cost need instrumentation when implemented and integrated.

The `app.observability.agent_nodes.instrument_node` wrapper supports the separate agent branch's router, draft, reviewer, human-review, clarification, and action nodes. It is **not active until integrated**. Once both branches are combined, import the wrapper into the agent graph and change the graph registration to `graph.add_node(name, instrument_node(name, node))`. Wrap each graph execution in a parent `observation("agent-workflow")` in the workflow service, and flush on application shutdown. The wrapper logs only allowlisted phase, route, reviewer outcome, revision count, and evidence count. Confirm context propagation and model-specific usage/cost on the integrated app with synthetic data before presenting a trace.
