# API contracts

## Implemented UI boundary

Interactive docs are at `/docs`; the generated contract is at `/openapi.json` and
`packages/contracts/openapi.json`. Public schemas live in `app/schemas/workflow_api.py`.

Claim lifecycle values now follow the [shared identity/status contract](identity-status-mapping.md).
Both APIs use canonical codes such as `gathering_evidence`; the UI renders friendly
labels. Repair progress and reported insurer outcomes are separate from claim and
run statuses. Clerk principal verification for the Python API is still pending.

| Method and path | Purpose |
| --- | --- |
| `POST /agent/runs` | Start a request; wait until a reviewed result, human pause, or failure. |
| `GET /agent/runs/{run_id}` | Read the current public result or pending action. |
| `POST /agent/runs/{run_id}/responses` | Resume the pending clarification or human decision. |
| `GET /artifacts/{artifact_id}` | Download an authorized, approved synthetic HTML packet. |
| `GET /health` | Process health; does not imply live integrations are connected. |

This MVP uses ordinary request/response HTTP, not a durable background queue. The UI can
show a loading state during POST and retain the returned run ID. GET is useful for reopening
a paused run or checking a duplicate request that returns `running`. Streaming can be added
without exposing raw graph state. Use one backend worker for the in-memory demo.

The demo expects `Authorization: Bearer <JEEVES_DEMO_TOKEN>`. Production login supplies
an async principal resolver to `create_app`. The user ID never comes from a public body.
Set explicit `UI_ORIGINS` for a browser running on a different local port.

### Start a request

```json
{
  "request_key": "unique-client-request-id",
  "policy_id": "demo-policy",
  "claim_id": "demo-window",
  "message": "I paid $150 to repair the window. Prepare the claim.",
  "explicit_route": "file_claim"
}
```

`explicit_route` is optional; chat can omit it and use the router. Allowed values are
`answer_claim`, `save_claim_status`, and `file_claim`. `claim_id` is optional for coverage;
updates and packets ask for a selected claim if one was not supplied. Creating cases,
uploading policies/attachments, dashboard lists, and login remain separate API workstreams.

Use the same `request_key` only when retrying an identical request. The server returns the
same run without starting another graph. A different body with that key produces HTTP 409.

### Response states

Every response includes `run_id`, data `mode`, `model_mode`, `status`, `route`, and completed
node `stages`. Optional result fields are null until they are safe to expose.

| Status | UI behavior |
| --- | --- |
| `running` | Keep waiting; retrieve the run again. |
| `completed` | Display the reviewed `answer` or saved/prepared `action_result`. |
| `awaiting_information` | Display `pending.questions` and collect clarification. |
| `awaiting_review` | Display `pending.draft`, estimate and cited evidence; offer approve/edit/reject. |
| `blocked` | Show review issues; the automatic revision limit has been reached. |
| `rejected` | Human rejected the action; nothing was saved/exported. |
| `failed` | Display the sanitized error; no unreviewed result is published. Start a new request after correction. |

`mode=fixture` means claim/policy/storage adapters are synthetic. `model_mode=fixture`
means deterministic model scripts; `model_mode=nebius` means actual Nebius calls against
those synthetic adapters. Neither label implies a real insurer submission.

Coverage `answer` is populated only after review passes. For an estimated payment of zero,
`answer.next_actions` contains `save_resolution` and `prepare_packet`. These start new
requests routed to `save_claim_status` or `file_claim`, with the user's explicit selection.
Sending `save_resolution` directly as a route is invalid.

### Respond to a pending action

Copy the exact `interrupt_id` and `artifact_version` from the current response. Example approval:

```json
{
  "request_key": "unique-approval-request-id",
  "interrupt_id": "copy-from-pending",
  "decision": {"artifact_version": 1, "action": "approve"}
}
```

An edit uses `action: "edit"` plus a nonempty `feedback` string. It regenerates the draft,
reviews it again, and returns a **new** pending action/version. A rejection uses `reject`.
Replaying an identical response key returns its original result; stale actions or conflicting
key reuse return HTTP 409. The final action adapter also deduplicates writes and checks the
claim version atomically. A claim changed by another request while awaiting approval causes
the run to fail rather than overwrite that change.

Clarification uses the same endpoint and exactly one `clarification` object:

```json
{
  "request_key": "unique-clarification-id",
  "interrupt_id": "copy-from-pending",
  "clarification": {"message": "Use the window claim.", "claim_id": "demo-window"}
}
```

The clarification `claim_id` is optional. A newly selected claim is checked for ownership
and policy association by the nodes before use. The UI cannot supply approval flags,
review results, or raw graph state; unexpected fields are rejected with HTTP 422.

### Files and failures

An approved packet returns `action_result.outcome=prepared` and an `artifact_id`.
Download it using the authenticated artifact endpoint. The current exporter produces
HTML that can be viewed/printed; it is explicitly synthetic and not an official insurer form.
`saved` represents an approved status/resolution update. `submitted` is not an MVP outcome.

Missing authentication in demo mode returns 401. Unknown/inaccessible resources return 404.
Unconfigured login or workflow adapters return 503. The run itself can return status `failed`
with HTTP 200 when model execution fails; the UI must inspect the response status field.
No internal prompts or raw exception/provider details are returned.

## RAG integration boundary

Agree on request and response field names before parallel UI, backend, agent, and evaluation work. The initial RAG boundary is defined in `apps/api/app/services/rag/types.py`:

- ingestion receives a policy ID, owner user ID, policy version, and PDF path;
- retrieval receives the authenticated user ID, selected policy ID, question, and result limit;
- returned evidence includes chunk ID, policy version, page, section, excerpt, and similarity score.

The storage adapter must scope retrieval by both user and policy. Resolve the user ID from the authenticated session; do not trust a browser-supplied owner ID.
