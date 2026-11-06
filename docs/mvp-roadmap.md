# Claim Companion — MVP integration roadmap

Updated: November 6, 2026

Requirements baseline: `SV-InsuranceAgent-requirements.pdf`, v0.2, November 5, 2026, supplied for this project. Section/page references below refer to that document; this change does not upload the PDF.

This file records the completed foundation, remaining integration work, recommended implementation order, and acceptance checks. It is a planning and handoff document, not a claim that the complete application is implemented.

## 1. Current status and evidence

**The database foundation is implemented and verified in CI. The complete user journey is not yet integrated or verified.**

| Area | Recorded status | Evidence / location |
|---|---|---|
| Six application tables | Implemented: `users`, `policies`, `policy_chunks`, `claims`, `messages`, `claim_events` | [`0002_application_schema.sql`](../apps/api/migrations/0002_application_schema.sql) |
| Migration tooling | Transactional runner with checksums, advisory locking, rollback, and refusal of missing/empty directories or incompatible migration history | [`migrate.py`](../apps/api/app/db/migrate.py) |
| Schema verification | Read-only checks for tables, columns, pgvector dimension, migration history, and key schema safeguards | [`verify.py`](../apps/api/app/db/verify.py) |
| Database tests | 49 passed, no skips: 17 migration-tooling checks and 32 PostgreSQL tests, for database commit `046ac35f4d25cbdcadfd942ce0e0798e425aabfb` | [Verified CI run](https://github.com/Shrezz/Jeeves/actions/runs/42295012849) |
| Restart persistence | CI restarted PostgreSQL and verified that six tables, the migration ledger, pgvector, and a committed synthetic record survived | Same CI run; [`restart_probe.py`](../apps/api/tests/database/restart_probe.py) |
| Database pull request | PR #1 is now merged into `capstone-scaffold`; earlier descriptions calling it unmerged are historical | [PR #1](https://github.com/Shrezz/Jeeves/pull/1), merged November 6, 2026 |
| Intended local/deployed database | Not verified or migrated through this work; CI success is not deployment evidence | Follow [`database.md`](database.md) |
| API foundation | `/health`, `/workflow/route`, and `/workflow/estimate`; route/estimate are read-only previews, not a persistent application workflow | [`main.py`](../apps/api/app/main.py) |
| RAG foundation | Page-aware PDF extraction/chunking and embedding/storage interfaces exist; end-to-end uploaded-policy retrieval remains to be integrated | [`services/rag/`](../apps/api/app/services/rag/) |
| Tracing foundation | The default-branch API now includes observation hooks for the route/estimate previews and a shutdown flush; live end-to-end trace delivery is not established by that code alone | [`main.py`](../apps/api/app/main.py) |

`schema_migrations` is an additional technical bookkeeping table, not a seventh application entity. The 49-test result is database/migration evidence only, not proof of login, UI, agents, policy answer quality, packet generation, or the full application.

### Existing work to reuse

- **Agent workflow:** work reviewed on `feat/agent-nodes-review` at commit `810b2ddb67a1a41bc17494dd3387620aa6152a6f` includes an executable agent workflow and UI-facing API. Its documented fixture demo uses synthetic evidence and in-memory state that resets on restart. Login, real policy indexing, and database adapters remain separate integrations. Reconcile its contracts with the persistent backend rather than rebuilding it blindly. [Reviewed README](https://github.com/Shrezz/Jeeves/blob/810b2ddb67a1a41bc17494dd3387620aa6152a6f/README.md).
- **Observability:** opt-in Langfuse instrumentation was reviewed on `langfuse-observability` at commit `ed9d7e76f2c6bfd6fb203e39c9a1eb8152786709`. Preview-route hooks are now also present on `capstone-scaffold`. Extend and verify this work for the complete workflow rather than treating tracing as wholly absent. [Reviewed tracing implementation](https://github.com/Shrezz/Jeeves/blob/ed9d7e76f2c6bfd6fb203e39c9a1eb8152786709/apps/api/app/observability/tracing.py).
- **Uploaded integration package:** the earlier prepared overlay is not evidence of a completed integrated app. Reuse components selectively; do not apply its older migration tree over the committed schema. See [`uploaded-backend-integration.md`](uploaded-backend-integration.md) for the historical audit.

These references identify inspected work, not a guarantee that separate branches are compatible, fully tested together, or already deployed.

## 2. Remaining work in recommended implementation order

Unchecked boxes mean completion has not been established for the integrated application. An implementation may already exist in a feature branch or uploaded package and still require reconciliation and verification.

### Step 1 — Apply and verify the intended development database

- [ ] Configure `DATABASE_URL` for the intended PostgreSQL instance and install the database dependencies.
- [ ] Run the committed migrations and the read-only schema verifier.
- [ ] Run the migration command again and confirm that no files remain pending.
- [ ] Record verification output and the tested commit without exposing credentials.

**Done when:** the verifier returns `"ok": true`, identifies all six application tables and `vector(1536)`, and a repeat migration run makes no schema changes.

From `apps/api`, after configuring the connection and starting the database:

```sh
python -m pip install -r requirements-db.txt
python -m app.db.migrate
python -m app.db.verify
python -m app.db.migrate
```

Use [`database.md`](database.md) for Docker Compose, Bash, PowerShell, and connection setup. The canonical directory is **`apps/api/migrations/`**, not the older overlay's `apps/api/db/migrations/`. Do not apply both trees or delete needed data with `docker compose down -v`.

### Step 2 — Authentication and database-backed APIs

Requirements: R1, R3, R4, R12; specification sections 8–9.

- [ ] Connect registration/login/logout to `users`, including duplicate-email and invalid-login handling.
- [ ] Use library-generated password hashes and framework-supported expiring sessions with HttpOnly cookies; clear the session on logout.
- [ ] Connect policy, claim, message, and event reads/writes to PostgreSQL.
- [ ] Resolve identity from the authenticated session and enforce owner filtering on every data read/write, including policy-chunk retrieval.
- [ ] Persist conversation history, draft work, approval comments, and final outcomes with appropriate transactions.
- [ ] Test with two users and verify that saved conversations remain available after an application restart.

**Done when:** users can register/login/logout, retrieve only their own records, and resume persisted conversations. Approval events and the corresponding claim changes must be written atomically when that action is connected in Step 5.

**Boundary:** the existing ownership-related foreign keys are not row-level security and do not replace authenticated API authorization or owner-scoped reads.

### Step 3 — Policy upload and real RAG

Requirements: R2, R6; specification section 7 and onboarding in section 8.

- [ ] Connect text-PDF upload to persistent file storage and visible parsing/ready/error states.
- [ ] Reuse page-aware extraction/chunking and preserve page, section, policy identity/version, text, and embedding metadata.
- [ ] Select and configure an embedding provider compatible with the schema's 1536-dimensional vector contract; any dimension change needs an explicit migration.
- [ ] Implement the database-backed chunk store and owner/selected-policy-scoped retrieval.
- [ ] Retrieve coverage and limiting provisions, and return section/page/excerpt citations.
- [ ] Confirm the extracted policy label and deductible during onboarding; calculate amounts in backend code.
- [ ] Ask for missing evidence or facts instead of inventing coverage.

**Done when:** a coverage answer cites the authenticated user's uploaded synthetic policy, not a hard-coded fixture, and parsing/retrieval errors are visible.

### Step 4 — Agent and reviewer integration

Requirements: R5, R7–R9, R13; specification sections 3, 5–7.

- [ ] Reconcile the existing agent workflow with the database-backed API contracts and real policy retrieval.
- [ ] Connect `answer_claim`, `file_claim`, and `save_claim_status` to their distinct behaviors.
- [ ] Honor the claim selected in the UI; clarify ambiguous requests or case selection. Confirm new facts/expenses before continuing a mixed filing request.
- [ ] Build a package containing incident facts, expense, evidence, coverage explanation, attachments, and missing fields.
- [ ] Use a separate reviewer model call returning `pass`, `revise`, or `needs_info`; it must not write final state or file anything.
- [ ] Allow at most one refinement and re-review per attempt. Unresolved issues return to the user and keep the claim pending.
- [ ] Preserve backend-owned arithmetic: an eligible $150 loss with a $1,000 applicable deductible produces a $0 estimate and an explanation, without automatically closing the case.

**Done when:** a filing request produces a reviewed draft, a reviewer can identify a real issue and trigger one correction, and unresolved facts produce questions rather than invented details. Coverage questions do not automatically create packets. Ordinary status updates use a confirmation preview, not the reviewer agent.

### Step 5 — Human approval and PDF export

Requirements: R10–R13; specification sections 5–6 and 9–10.

- [ ] Present the exact package/version with evidence, missing fields, reviewer results, editable comments, and the option to leave it pending.
- [ ] Check authenticated ownership and the current package version for every approval or final action.
- [ ] Save approval actor, time, comments, and approved version in an event, together with the claim update in one transaction.
- [ ] Material edits increment the version, clear approval, and require fresh review and approval.
- [ ] Generate a downloadable packet with a clear **"Prepared — not submitted"** label, synthetic details, incident facts, expense, coverage/deductible explanation, citations, attachment list, and comments.
- [ ] Mark a packet prepared only after successful generation; persist explicit failures and protect retries against duplicate actions.
- [ ] Support an explicitly approved "Resolve without filing" outcome without preventing the user from pursuing a below-deductible claim.

**Done when:** stale approvals are rejected, only the approved package version is exported, outcome/comments/history persist, and repeated requests do not duplicate final actions. A generated packet is never represented as a real insurance submission.

### Step 6 — Frontend, supporting files, and complete browser journey

Requirements: R1–R4, R10–R12; specification section 8.

- [ ] Integrate login/sign-up and policy onboarding with the real APIs.
- [ ] Integrate the dashboard, policy summary, new chat, selected claim, and saved conversation history.
- [ ] Connect chat, typed expense, attachments, and the evidence panel, with Ask / Prepare claim / Update status actions.
- [ ] Connect package editing, comments, approval/export, and resolution actions.
- [ ] Show a status/comment/attachment preview and require confirmation before saving the user-reported event; do not turn ordinary repair updates into technical workflow states or verified filing receipts.
- [ ] Persist original uploads and generated packets on persistent storage and retain their paths in PostgreSQL.
- [ ] Keep visible labels, keyboard-accessible controls, and understandable error/status messages.

**Done when:** the full flow works through the browser: login → upload policy → ask for coverage → inspect evidence → prepare/review → approve → download → reopen the claim → confirm a status update. Saved data and files remain available after restart.

### Step 7 — Traces, evaluations, and final integration verification

Requirement: R14; specification sections 11–12.

- [ ] Extend the existing tracing to router decisions, retrieval chunk IDs, model/tool inputs and outputs, reviewer feedback, revision count, latency, and token/cost data when available.
- [ ] Link traces to claim/session identifiers without recording passwords or session tokens; use synthetic data.
- [ ] Verify actual Langfuse trace delivery. Where credentials/setup block progress, export traces locally and record what remains unfinished.
- [ ] Connect the golden dataset to the actual workflow: at least 12 scenarios, 8 development and 4 held out, with related paraphrases in the same split and team-reviewed labels.
- [ ] Cover all three routes, below/above deductible, exclusions, missing cause, unsupported citation, reviewer correction, restart/resume, stale approval, and repeated-action protection. Check user isolation separately.
- [ ] Use LangSmith for offline evaluations, or export local cases/results and disclose the unfinished platform integration.
- [ ] Report route accuracy, relevant-evidence retrieval, citation support, arithmetic correctness, reviewer correction/failure, latency, and end-to-end pass count, including failures.
- [ ] Compare a small set with and without the reviewer; manually inspect explanation correctness. Do not treat reviewer agreement as ground truth or claim statistical reliability from this small dataset.
- [ ] Run integrated API/browser tests and review the combined changes before declaring the MVP complete.

**Done when:** one complete run is inspectable, actual measured results and failed cases are available, and the submission checklist below is demonstrated against the integrated application.

## 3. Scope boundaries

The MVP is a synthetic California homeowners broken-window journey. All demo policyholders, policies, receipts, and incidents must be fictional and labeled accordingly.

**Required:** login/onboarding, policy RAG, dashboard/chat, three routes, claim agent, separate reviewer with one refinement pass, human approval, downloadable packet, persistence, and a small evaluation report.

**Optional:** visibly simulated MCP/API filing and public claim-template search. Packet preparation/export satisfies the MVP filing/preparation requirement; a reliable local generic template is sufficient.

**Deferred:** real insurer filing, real policy research, multiple states/insurance products, scanned-document OCR, complex settlement calculations, and production authentication features such as social login, password reset, email verification, MFA, and profile management. Basic password hashing, expiring sessions, and owner checks remain required.

## 4. Submission acceptance checklist

Adapted from specification section 12. These remain unchecked because database CI does not establish application completion.

- [ ] Login, policy upload, and dashboard work together.
- [ ] All three routes are demonstrated.
- [ ] Coverage answers cite the uploaded synthetic policy.
- [ ] A reviewer identifies a real issue and the claim agent refines it.
- [ ] Missing facts stay pending after the one-refinement limit.
- [ ] Human approval precedes final resolution or packet preparation.
- [ ] The $150 loss / $1,000 deductible example correctly explains a $0 estimate.
- [ ] A second supported case produces a downloadable packet.
- [ ] Saved claims, status updates, and comments remain after restart.
- [ ] Trace and evaluation results are shown, including failures.
- [ ] Synthetic data, simulation, and prepared-versus-filed labels are clear.

## 5. Next focused milestone and maintenance

**Next implementation milestone:** authentication plus owner-scoped, database-backed APIs, after confirming the intended development database migration. This supplies persistent state for the existing agent workflow and frontend.

As each item is completed, replace its unchecked status with verified evidence: the implementation PR/commit, test run or demonstration, and the tested environment. Keep **implemented**, **integrated**, **tested**, and **deployed** distinct. Do not infer local deployment from a merge or CI run.

Related references: [database setup](database.md), [integration status](integration-status.md), [API contracts](api-contracts.md), [architecture](architecture.md), and [demo flow](demo-flow.md). Older notes may describe an earlier snapshot; use dated commits and test evidence to resolve status differences.
