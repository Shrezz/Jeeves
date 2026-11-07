# Agent nodes — first implementation checkpoint

The initial checkpoint provided independent nodes for review. The next checkpoint now
connects them in `app/agents/graph.py` and exposes the API. This guide describes the node
boundaries; see `backend-integration.md` for current execution status. No insurer submission exists.

## Review order

All paths below are relative to `apps/api/`.

| Order | File | Responsibility / output |
| --- | --- | --- |
| 1 | `app/schemas/agents.py` | Validated requests, facts, drafts, review outcomes, and human decisions. |
| 2 | `app/agents/state.py` and `context.py` | Workflow state versus injected, authorized runtime dependencies. |
| 3 | `app/agents/router.py` | Select one of three routes or request clarification. Explicit UI routes bypass the model. |
| 4 | `app/agents/answer_claim.py` | Read claim context and policy evidence; return an internal coverage draft and deterministic estimate. |
| 5 | `app/agents/save_claim_status.py` | Propose a status/facts/comment update. No database write. |
| 6 | `app/agents/file_claim.py` | Prepare packet content, incorporating user-reported changes and citing policy evidence. No export/submission. |
| 7 | `app/agents/reviewer.py` and `reviews/` | Use separate coverage, status, and packet checks. Publish coverage only after a pass. |
| 8 | `app/agents/human_review.py` | Pause with `interrupt`, validate approve/edit/reject, and reject stale decisions. No final write. |

Node functions are async, accept `(state, runtime)`, and return partial state updates.
They do not mutate the incoming state. The model adapter is a small wrapper around an
injected LangChain chat model. Generator and reviewer instances are separate dependencies;
the provider and model names can differ without changing node code.

## Implemented behavior

- Router preserves the full user message. "I paid $150; let's file" selects filing while
  retaining the repair update for packet preparation.
- Drafts have increasing artifact versions. Regeneration clears earlier reviews,
  published answers, and human decisions.
- Coverage drafts use `likely_covered`, `likely_not_covered`, or `unclear`. They never
  represent an insurer's decision. Unknown estimate inputs remain null.
- Python computes the simplified synthetic estimate: `max(covered_amount - deductible, 0)`.
  The reviewer must establish that the amounts and this calculation are appropriate for
  the evidence. This is not a general insurance payout calculator.
- Coverage and packet review check citation existence before calling the model. Status
  review is separate and does not fetch policy evidence.
- For packets, the reported cause must use wording from the homeowner’s account or confirmed
  incident fields. The reviewer first compares the factual fields and narrative with those
  sources, without seeing policy passages or previous AI answers. An unsupported detail goes
  back for revision. A separate coverage check can discuss a peril as a policy condition
  without asserting that it occurred.
- Coverage/packet reviewers request at most one supplementary policy search when semantic
  review identifies an evidence gap. Reused evidence still receives a fresh semantic review.
- Review results are `pass`, `revise`, or `needs_information`. A first revision requests
  regeneration; another failed review is `blocked`. Exceptions propagate, never pass.
- A passed coverage review populates `answer`; drafts remain internal. A zero estimate
  offers `save_resolution` and `prepare_packet`.
- Passed action reviews proceed to human review. Insurer updates remain explicitly
  `user_reported_*`; approval of an app action is a separate workflow phase.
- A human edit clears review and requests regeneration. A resumed decision must match
  the artifact version, and the claim's database version must still match the snapshot.
  Packet revisions carry the latest homeowner correction separately from earlier notes.
  Before returning a revised packet, the reviewer checks that its facts, coverage
  explanation, and open questions consistently reflect that correction.
- `approved` means approved for a future backend action, **not saved, exported, or filed**.

The frozen Pydantic objects validate field shapes, amounts, and allowed statuses. They do
not establish factual truth. The review prompts and future live-model evals address semantic
accuracy; a different reviewer model does not guarantee correctness.

## Integration boundaries

| Hook | Inputs / output | Integration expectation |
| --- | --- | --- |
| `StructuredModel.generate` | Prompt, JSON-compatible context, output schema → validated object | Inject separate generator and reviewer. Select Nebius models and verify structured-output support later. No provider credentials are read here. |
| `ClaimReader.load_claim` | Authenticated user ID + claim ID → `ClaimSnapshot` | Adapter enforces ownership and returns a versioned record. Missing/inaccessible claims raise. Nodes additionally verify owner, claim, policy, and version. |
| `PolicyReader.retrieve_evidence` | Authenticated user ID + policy ID + question + limit → existing RAG `Citation` objects | Adapt the existing synchronous retrieval service when integrating. Enforce owner/policy filtering and select the correct policy version. |
| `AgentContext.template` | Synthetic packet requirements | Injectable template value; no web lookup is required for this checkpoint. |

The existing RAG helper defaults to excerpts of 500 characters. The integration should
return sufficient source context for exclusions/conditions, rather than silently cutting
off a relevant clause. The node hook reuses the existing `Citation` type and leaves the
RAG implementation unchanged.

`user_id`, policy selection, and policy version come from trusted backend context. These
internal contracts are not public request bodies: the UI must never submit arbitrary
workflow state, reviews, approval flags, or owner IDs. Only the later authenticated backend
will translate UI requests and decisions into state changes and LangGraph resumes.

## Run the checks

From the repository root:

```bash
cd apps/api
uv sync --locked --group dev
uv run --locked pytest -q
uv run --locked ruff check app/agents app/schemas/agents.py tests
uv run --locked ruff format --check app/agents app/schemas/agents.py tests
```

Tests use explicitly scripted models and in-memory claim/evidence fixtures in
`tests/fakes.py`. They verify contracts and node behavior, not live model reasoning or
real RAG quality. Human-review tests compile a **one-node test graph** with an in-memory
checkpointer to exercise actual interruption and resume. That checkpointer is not durable
storage for the application. No model credits or network calls are used by the tests.

## Integration sequence after node review

The graph, API, model adapter, local tracing, and HTTP eval adapter below are now implemented.
The live database/RAG/auth integrations, durable run storage, and live model evaluation remain.

1. Confirm the contracts and node behavior; adjust these before graph wiring.
2. Configure Nebius generator/reviewer adapters, bounded timeouts/retries, and a small
   live-model compatibility check. OpenAI fallback remains disabled by default.
3. Connect claim/policy hooks to the team's implementations and replace test fixtures.
4. Wire routes, clarification/resume, one revision per automatic review loop, human edit
   regeneration, and failures into the full LangGraph workflow. Preserve progress across
   clarification turns; never reset the retry limit by rerouting a failed draft.
5. Add durable checkpointing and versioned, idempotent backend save/export actions.
   Recheck ownership, current claim/artifact version, and human approval immediately before
   committing a write. A check in the human-review node is not an atomic database guarantee.
6. Add the thin FastAPI run/status/response/artifact endpoints and OpenAPI examples. Return
   only reviewed answers, safe progress labels, or the specific pending human action;
   never serialize the entire graph state to the UI. Translate errors to pending/failed
   status rather than showing an unreviewed answer.
7. Integrate tracing and the existing eval runner. Evaluate coverage, status, and packet
   reviews separately using flawed and correct drafts, plus complete workflow scenarios.

Login/onboarding, UI, RAG ingestion/storage, and claims DB implementation remain separate
workstreams. `/health` is unchanged; the new endpoints are documented in `api-contracts.md`.
