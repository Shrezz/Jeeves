# Backend implementation handoff

## Execution checklist

- [x] Typed internal contracts and public API schemas.
- [x] Six nodes with separate coverage/status/packet review checklists.
- [x] A separate new-request initializer; router only classifies intent.
- [x] Evidence caching scoped by owner, policy/version, claim, and incident facts.
- [x] Graph connections, clarification interrupts, one automatic revision, and human review.
- [x] Nebius structured-output adapter with a timeout and at most one transport retry.
- [x] Separate generator/reviewer configuration; no automatic paid-provider fallback.
- [x] Approved-action and artifact-reader hooks, plus a synthetic in-memory implementation.
- [x] FastAPI endpoints, bearer-auth hook, explicit CORS origins, and OpenAPI export.
- [x] Local JSON tracing and an evaluation adapter using the same public API as the UI.
- [x] Offline node, graph, API, ownership, retry, cache, and approval tests.
- [ ] Connect the separately developed authenticated-session resolver.
- [ ] Connect the real embedding/vector store through `PolicyRagAdapter`.
- [ ] Implement the claims read/write and artifact hooks using Postgres/file storage.
- [ ] Persist run metadata, deduplication receipts, and LangGraph checkpoints together.
- [ ] Run compatibility and quality evaluations using the chosen Nebius models/account.
- [x] Add optional Langfuse tracing and a local-data Langfuse experiment runner.
- [ ] Verify traces and experiment exports against the team's Langfuse project and selected live models.

The unchecked items are integrations or live validation, not silently simulated production
capabilities. The demo is intentionally single-process, in-memory, and synthetic. It can
resume paused runs while the process remains alive; it cannot recover after restart.

## Graph and retrieval behavior

`app/agents/graph.py` is the source of truth. `begin_request` resets transient outputs
once, followed by routing. Automatic refinement and human/clarification resumes never
re-enter that reset step. Every regenerated draft receives a new artifact version.

Coverage answers become public only after review passes. Action drafts become available
for human approval only after the relevant review passes. After approval, a deterministic
commit node invokes the action adapter. There is no direct insurer submission or email.

An exact retrieval query for the same incident can reuse passages. Later filing can reuse
reviewed passages after a small model relevance check. A changed confirmed cause/date/
description or policy version changes the cache key. Repair cost is excluded from that key,
but estimates and reviews are always regenerated. A changed cause in a new message is
presented to the relevance planner; uncertainty requires a new retrieval. Reuse is an
optimization of passages, never reuse of a coverage verdict or human approval.

The reviewer starts with existing evidence. If it identifies a policy evidence gap, it
returns a targeted `evidence_query`; the backend runs one additional retrieval and one
more review call. Unresolved gaps then go to the user. Status reviews do not retrieve policy.

## Where each integration attaches

| Integration | Contract / implementation |
| --- | --- |
| UI | `app/schemas/workflow_api.py`, `app/api/agents.py`, `/openapi.json` |
| Authentication | Async `principal_resolver(request) -> user_id`, supplied to `create_app` |
| Authorized selection | `ContextFactory(user_id, policy_id, claim_id) -> AgentContext` |
| Model access | `StructuredModel.generate`; `NebiusModel` implements JSON-schema calls |
| RAG | `PolicyReader.retrieve_evidence`; `PolicyRagAdapter` wraps existing RAG service |
| Claim reads | `ClaimReader.load_claim`, returning an owned, versioned snapshot |
| Final writes/export | `ApprovedActions.commit`; owner/version checks and idempotency must be atomic |
| Downloads | `read_artifact(user_id, artifact_id)` returning content, filename, media type |
| Checkpoints | `build_graph(checkpointer)`; use `checkpoint_serializer()` with a durable saver |

The actual DB adapter must check the request key first for a matching replay, then perform
the version comparison and final writes in one transaction. Persist the confirmed changes,
resolution note or packet evidence, event record, and artifact reference together. Missing
adapters raise instead of reporting a successful save. Prepared is distinct from submitted.

For deployment, changing only the checkpointer is insufficient: `WorkflowService` currently
stores its run index, owner/context association, locks, and response receipts in memory.
Replace that run storage too, recreate authorized runtime context on resume, and provide
cross-process concurrency controls before using multiple workers. Keep `user_id` and
policy version derived from the backend; never let the UI patch raw graph state.

## Models and diagnostics

`MODEL_MODE=fixture` uses deterministic scripts solely for integration tests/demo.
`MODEL_MODE=nebius` uses real model requests with the same synthetic policy/claim adapters.
The API reports data `mode` separately from `model_mode` to make that distinction explicit.
Model IDs in `.env.example` are candidates, not a quality guarantee or account-availability
check. Live calls have not been run as part of the offline test suite.

Local JSON trace events include node completion, run timing/errors, cache hits, and actual
token counts returned by Nebius. They omit policy text, messages, and credentials. Token
counts are not fabricated for fixtures. Provider prices/cost totals are not assumed.
With `LANGFUSE_TRACING_ENABLED=true` and valid credentials, Langfuse traces also cover workflow nodes, retrieval, and Nebius generations. Only actual provider usage is captured; model cost requires configured pricing. See `architecture.md` for the opt-in synthetic-content policy and `evals/README.md` for experiment setup.

## Optional public web search

In demo mode, set `KEENABLE_SEARCH_ENABLED=true` and optionally set `KEENABLE_API_KEY` in the local environment. The keyless public API is rate-limited; an API key uses Keenable's authenticated endpoint and may incur usage charges. Supply `web_search_query` in a start-run request only when a public search is wanted. The exact query is sent to Keenable, so do not include policyholder information, claim details, or other confidential content. The app does not automatically send the claim or policy as a query.

The agent runs one bounded search and returns up to three external links in `web_search`; this field is separate from policy `citations`. Web results are not passed into coverage generation or review and cannot establish coverage. A provider failure or disabled integration returns `unavailable` and leaves the claim workflow running. Langfuse records the provider and result count, not the search query or results. The existing frontend does not yet expose the search request or display these results. Production context factories must inject a `KeenableSearch` instance explicitly.

API reference: https://docs.keenable.ai/api-reference/search.md

## Verification

From `apps/api`, use `uv sync --locked --group dev` then `uv run --locked pytest -q`.
The tests cover actual LangGraph interruption/resume and full API flows, including edits,
duplicate submissions, foreign-owner access, stale approvals, cache invalidation, blocked
refinement loops, and provider errors. HTTP transport is mocked in provider tests.

`evals/run_eval.py` calls the public API and leaves unmeasured criteria unscored. Its
stale-approval probe performs an edit and sends an invalid approval only in fixture mode.
`evals/fixture_suite.py` runs the 12 scenarios in separate synthetic in-memory fixtures,
including simulated approvals, and compares draft citations before and after review.
See `evals/README.md` for the reports and remaining integration limits.
