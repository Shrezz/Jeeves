# Jeeves observability operations

## Supported deployment and release gate

The integrated Express → private Python worker → local RAG worker path is instrumented.
It supports a single-host deployment with persistent PostgreSQL and a persistent Chroma
directory; this does not turn the embedded vector store into a distributed service.
The standalone FastAPI fixture demo is not a production database implementation.
When tracing is enabled, Express startup requires the instrumented workflow runtime.
Production also rejects incomplete telemetry configuration, preventing use of the
legacy unreviewed hosted claim-chat fallback.

Required server configuration:

```dotenv
LANGFUSE_TRACING_ENABLED=true
LANGFUSE_BASE_URL=https://us.cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=... provision through your secret manager ...
LANGFUSE_SECRET_KEY=... provision through your secret manager ...
LANGFUSE_TRACING_ENVIRONMENT=production
LANGFUSE_RELEASE=... immutable build or commit identifier ...
LANGFUSE_CAPTURE_SYNTHETIC_CONTENT=false
CLAIM_CHAT_ROOT=... deployed apps/api directory ...
LOCAL_RAG_ROOT=... deployed RAG directory ...
LOCAL_RAG_DATA_DIR=... persistent vector-index directory ...
```

The launcher deliberately uses `development`, not `production`. Use `verification`
for synthetic probes. Production requires HTTPS, a non-local release, and no detailed
content capture. Restart processes after changing configuration. Keep credentials out
of frontend variables, source control, build artifacts and logs. The tested Python SDK
is Langfuse 5.2.0 from the API lockfile. Use the locked API dependencies.

## Trace contract

| Operation | Root / children | Interpretation |
| --- | --- | --- |
| Dashboard turn | `dashboard-chat`, agent nodes, `chat-guidance`, model calls and retrieval | Conversation ID is the session; each invocation has its own trace |
| Claim start/resume | `ui-claim-workflow`, agent nodes, generations, human review, commit | Run ID is the session; approval/edit/clarification can produce more traces |
| Policy upload/search | `local-policy-index` / `local-policy-search`, extraction, embedding, vector search | Child searches inherit traceparent/tracestate from Python |
| Model invocation | `model-call` with one `model-generation` per actual attempt | Each generation records role, model, prompt digest, available usage and failure state |
| Reviewed answer | `chat-guidance` | `reviewed`, `conditional_fallback`, or `abstained`; abstention is a warning, not verified coverage |

Graph nodes use `agent`, embeddings use `embedding`, and vector lookup uses `retriever`.
Human interrupts are expected pauses, not exporter/application errors. Review failures,
transport failures and killed workers are separate signals. Missing provider usage or
pricing remains missing: it must not be presented as zero cost.

Environment/release propagate to dashboard, claim and RAG workers. Raw prompts,
policy wording and answers are omitted by default. Synthetic opt-in is restricted to
demo/allowlisted claims and is blocked when tracing environment is production.
Prompt hashes identify template changes without sending prompt contents. Do not use
raw customer IDs as new tags or metrics dimensions.

Telemetry initialization/update/close failures preserve application behavior. Each flush
has a five-second application wait budget and a safe warning on timeout. SDK network
requests use a five-second timeout. One-shot Python workers explicitly close database
and vector-store contexts, flush standard streams, then exit without rerunning the
SDK exit hook. This prevents a second unbounded flush from holding a completed
response. This boundary does not change long-lived API/library lifecycles. Traces are best effort,
not an authoritative audit ledger. PostgreSQL holds approvals and committed actions.
A process kill can lose its final trace: monitor `worker_failed` logs independently.

## Evaluation integrity

Existing checks cover route, workflow phase, policy-page quote integrity, conditional
payment and explicit human annotations. Unannotated semantic support is unscored.
UI score export requires the same route, phase, artifact version **and SHA-256 of the
exact saved content/sources/workflow** as the latest completed trace. Old traces without
the fingerprint are intentionally ineligible. Re-run the synthetic workflow to evaluate
an older deployment. Score IDs, names, and timestamps are stable across retries; score environments come from the matched root rather than the evaluator shell. Readback verifies values, environment, timestamp date, and absence of duplicate IDs. The CLI fails if requested export remains unverified.
Observation reads paginate with a bound; score verification polls for up to 30 seconds
for eventual ingestion, verifies submitted values as well as IDs, and returns `submitted_not_yet_visible` rather than a false pass.

The current APIs are SDK observations and scores (modern endpoints), and SDK experiments.
The dashboard provisioning tool isolates the explicitly unstable dashboard API. Do not
use deprecated trace/session/dataset-run REST endpoints in new tooling.

## Verification commands

From the repository root, using the installed runtimes:

```sh
apps/api/.venv/bin/python -m pytest apps/api/tests --ignore=apps/api/tests/database
(cd apps/web && pnpm test && pnpm run typecheck)
(cd RAG && .venv/bin/python -m pytest tests)
```

Database tests require an isolated PostgreSQL server with pgvector, a database name
ending in `_test`, and a role with CREATEDB. They create/drop separate test databases.
Never substitute the application DATABASE_URL.

```sh
TEST_DATABASE_URL=... REQUIRE_DATABASE_TESTS=1 apps/api/.venv/bin/python -m pytest apps/api/tests/database
```

For real model, retrieval and checkpoint verification, load server variables in your
shell, set TEST_DATABASE_URL to a disposable server, set tracing environment to
`verification`, then run from `apps/api`:

```sh
.venv/bin/python -m scripts.verify_observability
```

This probe uses only the checked-in fictional PDF, creates/removes a test database and
vector index, exercises dashboard review, policy isolation, clarification, stale and
cross-owner approvals, and a durable local packet commit. It prints measured quality
failures separately from workflow completion. It does not sign in through Clerk, send
real claims, or prove semantic correctness. Run authenticated browser acceptance separately.

The existing fixture suite remains useful for deterministic adversarial paths:

```sh
apps/api/.venv/bin/python evals/fixture_suite.py evals/datasets/dev.jsonl --fail-on-failed --langfuse --run-name BUILD_ID --output reports/workflow-dev.json
```

Do not tune against held-out data. Do not interpret fixture-model passes as real-model
quality. Keep live probe reports and human annotations with your release evidence.

## Operations dashboard and alerts

`evals/monitoring/dashboard.json` defines **Jeeves Operations**: request count by
environment, p95 request latency, errors by operation, model tokens, measured Boolean
check pass rates, and unscored checks. Provision with the API venv and pnpm on PATH:

```sh
apps/api/.venv/bin/python evals/monitoring/provision_dashboard.py
```

Filter by environment before judging production. Drill into a trace before interpreting
an error count: expected stale/unauthorized approvals in verification deliberately fail.
Boolean quality charts exclude unscored checks; the separate unscored tile shows the gap.
The provisioning script does not replace the project's Home dashboard.

Suggested initial operational alert rules (calibrate after representative load):

- Any `telemetry_export_failed` log: inspect collector credentials, region, network and quotas.
- Any `worker_failed` with `killed=true`: investigate timeout/OOM and incomplete traces.
- No traces despite confirmed application traffic for 10 minutes: verify exporter health.
- Sustained root error rate above 5% over 15 minutes with at least 20 requests: investigate.
- p95 latency above the application's agreed response-time objective: inspect retry/model spans.
- Any measured citation-integrity failure in the approved synthetic suite: stop rollout.

Alerts are intentionally disabled at the owner’s request. Future notification delivery
requires a configured monitoring/on-call destination. A dashboard alone is not alert
delivery. No recipient or webhook is embedded in this repository.

Before production rollout, record the deployment host, secret manager, backups/retention,
the explicit decision to leave alerts disabled, and a signed-in acceptance run. The local setup does not verify
those deployment-specific controls. No telemetry tool can prove the model's insurance
answers correct; retain human semantic review and the explicit approval boundary.

## Local verification record (2026-11-09)

- API: 246 tests; web: 60 tests and TypeScript checks; RAG: 16 tests; isolated PostgreSQL: 61 tests passed.
- Fixture experiment: 22 checks passed, 0 failed, 6 unscored.
- Real model probe: 10 Boolean checks passed, 2 human checks unscored. All 11 score records (including the unscored count) read back from Langfuse.
- Real retrieval spans linked to their parent trace; all 12 model generations reported token usage and generator/reviewer roles. Environment `verification`, release `jeeves-observability-v1` propagated throughout.
- Stale and cross-owner approvals rejected; reviewed packet committed once. Dashboard answer abstained and is recorded as a warning, not a quality pass.
- Collector outage probe returned successfully with a safe export warning in 3.64 seconds.

[Verified packet trace](https://us.cloud.langfuse.com/project/cmw4i59d000r1ad0jp0w108e8/traces/8d2045f3b5c23655b12584153011f61f)

Local reports: `reports/observability-live.json` and `reports/observability-fixture.json` (gitignored).
This initial evidence applies to the local stack. The subsequent signed-in acceptance record is below; no production-host deployment has been verified.

## Coverage map

| Surface | Appropriate observability | Verification / limitation |
| --- | --- | --- |
| Express HTTP, Clerk guard, policy/claim CRUD, evidence uploads/downloads | Request ID, method, URL without query, status, duration; safe error type logs | Auth guard stays in place. These operations do not need LLM generations. Signed-in browser acceptance is separate. |
| PDF declarations reader | HTTP timing plus safe worker failure/invalid-response events | Deterministic extraction; no model call and no customer PDF text in Langfuse. |
| Policy upload/index/search | Extraction, chunking, embedding, retrieval spans; ingestion failure event and persisted failed state | Real fixture PDF and MiniLM/Chroma exercised, including owner/policy isolation. |
| Dashboard chat | Root/session, router, handoff, guidance review, generation roles/usage, retrieval, abstention | Scope rejections before the worker have an HTTP log event. The boarding test abstained; it is not a quality pass. |
| Claim answer, packet, status update | Each graph node and model call; bounded retries/review; human pause/edit/reject/approve/commit | Deterministic scenarios cover routes. Live packet approval and durable checkpoint resume verified. |
| Optional public web search | Keenable tool span, safe query length/result count and errors | Remains disabled for the local demo. Provider behavior is tested with controlled responses; no live paid-provider claim is made. |
| Ollama and hosted JSON-schema adapters | Individual generation attempts, provider-reported tokens, prompt digest, generator/reviewer role | Ollama exercised live. Hosted adapters exercised with controlled transport responses; hosted credentials/quotas are deployment-specific. |
| Injected LangChain model adapter | Generation, schema validation and available raw token usage, without raw output capture | Structured-output and privacy tests. Provider-managed internal retries are inside the adapter call. |
| FastAPI fixture/demo API | Workflow/session, routing/estimate helpers, all agent nodes, RAG adapter | Fixture tests and Langfuse experiment export. In-memory demo is not a production backend. |
| Standalone `policy_rag.api` library | Safe request/step, generation, embedding and retrieval spans; bounded flush | Real SDK hierarchy/privacy tests with in-memory exporter. Detailed local JSON traces are disabled in production. |
| Nested RAG subprocess exporter | Safe failure flag returned in private worker JSON, forwarded to parent logs | Export failure cannot silently disappear merely because nested stderr is suppressed. |
| Evaluation tools | Existing approved checks, exact-result trace binding, deduplicated export, score readback | Executed explicitly for synthetic runs. This is not an automatic semantic score for every user request. |
| Unused audio/batch SDK scaffolding | No application route invokes these helpers | Not part of the running product. Any future route must receive tracing and acceptance tests before activation. |

The old direct hosted claim fallback is unavailable whenever tracing is enabled and in
production. The supported demo uses the instrumented Python workflow. Do not disable
tracing to bypass this startup gate.

No browser analytics, session replay, or raw customer-content capture was introduced.
Operational logs and the database cover non-AI behavior; Langfuse covers AI execution
and measured evaluations. Alerts remain disabled by request.

## Demo reliability follow-up

A later live run exposed a blocked packet: its reviewer demanded arithmetic already
provided by the server and overlooked an existing conditional qualification. The packet
review instructions now explicitly distinguish missing arithmetic from contradictions.
Citation retries now receive the previous draft and the specific mismatched source.
Strict quotation validation, independent review, and the human approval boundary remain.

After these changes, the packet reached approval with 10 automated checks passing and
both semantic checks unscored. The longer dashboard payment question still abstained;
a separate simple deductible question returned two verified quotes in 6.7 seconds.
See `docs/demo.md` for tested prompts, trace links, and the clearly labeled fallback.

Final combined demo run: session `1532212b-8b77-4daa-a76f-cfd1f14e9e89`.
Two dashboard citations, packet completed, stale/cross-owner approvals rejected,
10 measured Boolean checks passed, 2 semantic checks unscored, exact score readback
verified. Report: `reports/demo-full-flow.json`. Total regression tests: 383;
full web/API build and TypeScript checks passed. The subsequent authenticated browser record is below.


## Authenticated browser acceptance (2026-11-09)

The Clerk-authenticated journey uploaded and indexed the exact fictional PDF (five
passages), retrieved policy excerpts, answered the deductible question with two citations,
prepared a packet, and approved it locally. The saved claim is `prepared`, the workflow
is `completed`, and exactly one durable commit exists. The approval result fingerprint
matches the Langfuse root output.

- Session: `2169450d-3c35-44b8-9e2f-773de663fa0c`.
- [Packet trace and measured scores](https://us.cloud.langfuse.com/project/cmw4i59d000r1ad0jp0w108e8/traces/1b58c27f7d4da59b08d526360b14be3a): 29.02 seconds, six model generations, 12,459 provider-reported tokens, one automatic revision before reviewer pass.
- [Approval trace](https://us.cloud.langfuse.com/project/cmw4i59d000r1ad0jp0w108e8/traces/6589bacd8e4e8a830c2e78699191c0b4): human approval, commit node, completed root.
- Eleven Boolean checks passed; two human semantic checks remain unscored. All twelve score records were read back with the exact submitted values and inspected in the signed-in Langfuse interface.
- Reports: `reports/demo-signed-in-review.json`, `reports/demo-signed-in-approved.json`, `reports/demo-signed-in-observations.json`.
- Download content and the export link are present. Browser automation could not save the data URL; the owner subsequently confirmed successful manual download.

The first two browser attempts were blocked by reviewer false positives, including
requests for a calculation already present in the UI. The reviewer now receives the
server-calculated estimate inside the packet artifact as well as its existing context;
server arithmetic, unknown-input handling, factual checks, and approval gates are unchanged.
This input correction passed the subsequent browser attempt. Do not interpret that as
an accuracy guarantee. The earlier failures remain in the claim history and telemetry.

Reviewer revision/blocked spans now use `WARNING`, and a blocked UI workflow root uses
`WARNING` too. Expected clarification and human-review pauses remain normal states.
The signed-in trace visibly records the first review warning and later pass. The existing
error chart measures `ERROR`; use observation level filters to inspect warnings separately.
These levels follow the [Langfuse log-level contract](https://langfuse.com/docs/observability/features/log-levels).

After the final code changes, API tests reported 278 passed and 43 database-dependent
skips; those 43 database tests passed in the earlier isolated PostgreSQL run. Together
with the 60 web and 16 RAG tests, 397 distinct tests have passed across the local runs.
The fixture regression remains 22 passed, zero failed, six unscored. These tests check
contracts and safeguards; live model reliability and production-host controls remain
separate acceptance concerns. Alerts remain disabled.


### Latest clean-rehearsal failure remains open

After the successful signed-in run, a fresh isolated rehearsal still blocked on reviewer
requests to repeat the deductible calculation in narrative text. The structural review
input correction has not established consistent model behavior. The successful saved
packet is a usable demo fallback, but fresh generation is not certified as seamless or
production ready. No approval or validation guard was weakened.

The [failed trace](https://us.cloud.langfuse.com/project/cmw4i59d000r1ad0jp0w108e8/traces/30852de863e31bdd2427b5325dcc1347)
(session `cf9fe61e-5b1d-4aed-9530-4d804595729f`) retains reviewer warnings. Its exact
saved projection was evaluated: six failed workflow/citation-availability checks, one
passing route check, and five unscored checks; all eight score records were read back.
Missing packet citations describe a blocked output, not a finding that a displayed
quote was fabricated. Reports: `reports/demo-clean-retest-failure.json` and
`reports/demo-clean-retest-eval.json`.

The readiness script now evaluates and exports blocked preparations before reporting
failure. It skips approval probes when no human-review interrupt exists, leaving those
results unknown. Probe roots also warn when blocked. This removes a success-only bias
in the rehearsal export while retaining the approved metric set. Remaining production
work includes representative model/reviewer calibration and deployment-specific controls;
the observability implementation does not establish either by itself.


## Langfuse integrity audit follow-up (2026-11-09)

A live recheck found intact parentage for the successful packet, approval, and failed
rehearsal traces; all six generations in each preparation trace had provider usage.
Three exporter defects were corrected in `evals/ui_workflow_eval.py`:

- Scores now explicitly use the matched root's environment. Previously a backfill shell
  could tag a `verification` trace's scores as `development`.
- Score timestamps are anchored to the root start time, alongside deterministic IDs and
  unchanged names. Langfuse's score identity includes timestamp date, so IDs alone did
  not prevent duplicates across days. Readback now checks environment, timestamp date,
  values and duplicate IDs.
- The standalone CLI returns nonzero if requested score delivery is unverified, even
  when all local checks pass. Previously even `--strict` could exit zero in that case.

The focused evaluator suite passed 13 tests, including different shell/root environments,
wrong-date readback, duplicate scores, and unverified-delivery exit behavior. These changes
only affect evaluation export; the demo workflow and approved metric set are unchanged.
The timestamp behavior follows the [score update contract](https://langfuse.com/docs/evaluation/evaluation-methods/scores-via-sdk#preventing-duplicate-scores).

Historical repair is not yet verified: the eight scores on trace
`30852de863e31bdd2427b5325dcc1347` were resubmitted with the same IDs, names, values and
timestamps and the requested `verification` environment. The service accepted the batch,
but readback still returned `development`. No records were deleted or assigned new IDs.
Do not use environment-filtered aggregate scores for that historical run as if corrected;
inspect its exact trace and score values. See
`reports/langfuse-score-environment-correction.json`.

The audit identified missing blocked/warning widgets, immutable provenance, and an
end-to-end export timeout. Those implementation gaps are addressed in the final
hardening described below. Semantic labels and model/reviewer calibration remain
separate acceptance work. Alerts stay disabled.


Live exporter verification after the fix used the existing failed signed-in run
`5620c158-f28e-4747-bad8-e65ddf141e58` with the evaluator shell deliberately set to
`verification`. Its trace is `development`; all eight score records correctly used
`development`, their values and anchored timestamp date passed readback, and the CLI
exited 1 for the measured failures. Result: one pass, six failures, six unscored.
Report: `reports/langfuse-hardened-export-live.json`; trace
`3fcee1d575890ba8e1c7d0179b069a28`. This validates new exports without claiming the earlier
historical environment repair succeeded.


## Final hardening (2026-11-09)

The integrated UI score exporter now uses `jeeves-ui-v2`. Each score includes the
exact evaluator implementation SHA256, complete case SHA256, source release,
artifact version and result fingerprint. Deterministic IDs include evaluator and
case hashes; timestamp is anchored to the trace's UTC start date. Full score
readback validates identity and provenance, not just the numeric value. A total
45-second child-process deadline bounds all API work, and each request disables
automatic retries. Partial acceptance and unknown delivery are explicit failures.
`evals/README.md` describes artifact-bound human annotations and CLI behavior.
The approved metric set is unchanged; missing semantic labels remain unscored.

The local launcher computes a source/dependency-manifest release before starting
workers, including uncommitted demo changes. `scripts/build_release.py --output
reports/release-manifest.json` records reproducible file digests without reading
secrets, customer data, downloaded models or build output. For a deployment, compute
this identity from the final source snapshot and set `LANGFUSE_RELEASE` in the server
environment. It identifies the source and dependency manifests, not an audited
container image or resolved runtime environment.

The operations dashboard has separate warnings, blocked-packet and abstained-answer
widgets. Quality aggregates select both `jeeves-ui-v2` and its exact implementation
hash. Reprovision after changing evaluator code. Historical v1 records remain
inspectable; the eight historically mistagged scores described above were not
deleted, and their environment correction has not been claimed as successful.
The dashboard does not mix those legacy records into current v2 quality aggregates.
No alert delivery was configured, as requested.

Worker subprocess tests reproduce a stuck exporter: a completed response now exits
in 5.3 seconds after a safe timeout warning. Actual RAG indexing survives explicit
close and worker exit and is readable from a fresh worker. Provider usage logs
accept only validated numeric token fields, dropping arbitrary provider extras.


Final regression results: 494 API tests passed with the disposable PostgreSQL
database enabled (zero skipped), 60 web tests passed, and 21 RAG tests passed.
TypeScript checks and both web builds passed with the required local `PORT` and
`BASE_PATH` configuration. The deterministic development fixture reported
22 passes, zero failures and six unscored human checks. The app restarted with
release `jeeves-dcb69958a1a4d67d1539`; UI and API health endpoints returned HTTP 200.
The web build reports a bundle-size advisory; dependencies also emit Python
3.15 deprecation warnings. Neither is an evaluation pass/fail signal.

The final fresh live rehearsal again returned a cited deductible answer, then
blocked packet preparation. Its session is `042f8d75-a338-44a7-8ebe-1b7647ac0da8`;
trace `5a8430155a22d3a460feefcd98640876` records the blocked root as `WARNING`.
Six measured workflow/citation-availability checks failed. Approval probes were
not executed and remain unknown. Initial score export failed without delivering scores. Its timing and the subsequent
successful read-only lookup point to ingestion lag exceeding the ten-second window.
The lookup window is now thirty seconds within the same hard export deadline,
and an unmatched root returns `trace_not_visible_or_mismatched` / `not_sent`.
This does not turn blocked workflow results into successful packets.


The final v2 exporter was verified through the normal database-backed evaluator on
saved run `5620c158-f28e-4747-bad8-e65ddf141e58`, without modifying its blocked state.
All eight scores were read back with exact value/type/name/date/environment/subject
and provenance matches: one pass, six failures, five unscored. CLI exit 1 correctly
reflects measured failures, despite verified delivery. The evaluator shell was set
to `verification`; scores correctly inherited the trace's `development` environment.
Report: `reports/final-persisted-score-export.json`.

All nine dashboard widgets were persisted and read back with evaluator SHA256
`04122060e1f47bc11ee2a7d1db3f70637a3a1d3a43671a07531748280f528f7a`.
Quality charts currently contain that version's measured failed-case evaluation;
they are not a representative accuracy estimate. The successful signed-in rehearsal's
older scores remain visible on its trace.

The final trace audit found 63 observations across four related trace trees, zero
missing parents, and ten model generations with complete provider usage. Fifteen
nested RAG observations were present in their trace trees but lacked their own
session attributes. The Python-to-RAG boundary now forwards only the opaque session
ID explicitly, alongside the existing trace context, so observation-level session
filters include these children. Standalone indexing naturally precedes the workflow
session; it has its own correctly parented trace. No raw text or arbitrary baggage
was added to propagated metadata.


The final session-propagation check passed in Langfuse: trace
`a05bbc21fb110727e6b91b6fa3f42cea` has five observations, and the session filter returns
all five, including the RAG worker, embedding, and vector lookup. Parentage,
`verification` environment and release match. Report:
`reports/final-session-propagation.json`. The app was restarted on final source release
`jeeves-5222820a177d5f247b89`; UI and API health checks returned HTTP 200. Final tests:
494 API/database, 60 web, 21 RAG (575 total), all passing. The disposable test database
was stopped; the application database and saved approved packet are preserved.
