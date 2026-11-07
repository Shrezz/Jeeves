# Shared identity and status contract

This first integration step extends the existing UI schema. It establishes Clerk
ownership and consistent claim status values in the UI, Express API and Python
agent contracts. It does not connect the Python agents to the UI database yet.

## Identity

| Boundary | Value |
| --- | --- |
| Authenticated Clerk session | `user_…` subject |
| `users.id` | The same Clerk subject, stored as text |
| `policies.owner_id`, `claims.owner_id` | The same subject, foreign key to `users.id` |
| Agent/RAG `user_id` | The same subject; no generated UUID or email lookup |

Express uses the verified Clerk session to create an idempotent local profile row
before protected routes run. Optional name/email fields are profile data; Clerk
handles authentication. No password is stored. Existing owner-scoped queries and
claim-to-policy ownership checks remain. Foreign keys alone do not authorize access.

Python identity helpers validate identifier shape and map an owned record; they
do **not** verify tokens. A Clerk principal resolver still needs to be connected
to the Python API. The fixture demo keeps `demo-user` and demo authentication.

## Claim lifecycle

| Stored/API value | UI label | How it is set |
| --- | --- | --- |
| `draft` | Draft | New claim or explicit manual update |
| `gathering_evidence` | Gathering evidence | Evidence/chat activity on a draft or manual update |
| `preparation_requested` | Preparation requested | Explicit preparation request |
| `prepared` | Package prepared | Successful packet creation after human approval |
| `filed_by_user` | Filed by me with insurer | User reports that they submitted it |
| `insurer_decision_received` | Insurer decision received | User reports an insurer decision |
| `resolved_without_filing` | Resolved without filing | Explicit user choice |

These are shared values, not a complete transition engine. `prepared` and
`preparation_requested` are excluded from manual status inputs. The Python
approved-packet adapter sets `prepared` after export; the UI preparation action
still records a request until agent integration exists. Neither a request nor a
prepared packet means the insurer received a claim.

Keep these independent:

| Meaning | Location / allowed values |
| --- | --- |
| Repair progress | `claims.incident_json.repair_status`: `unknown`, `scheduled`, `completed` |
| Reported insurer outcome | `claims.insurer_outcome`: `unknown`, `approved`, `partially_approved`, `denied` |
| Outcome provenance | `claims.insurer_outcome_source`: `user_reported` or null; known outcomes require a source |
| Workflow execution | `running`, `awaiting_information`, `awaiting_review`, `completed`, `blocked`, `rejected`, `failed` |
| File upload | `pending`, `saved` |
| Policy indexing | `not_started`, `processing`, `ready`, `failed` |

Upload/indexing values are defined for later wiring; this step does not add
indexing state to UI policy rows. Repair/outcome fields are available in the DB
and Python contracts; exposing them in UI responses is a later adapter step.
The existing manual UI status endpoint remains separate from agent human review.

## Compatibility mappings

The Python adapter helper translates earlier values without authorizing a write:

| Earlier value | Mapping |
| --- | --- |
| UI display labels, e.g. `Gathering evidence` | Canonical code `gathering_evidence` |
| `open` | Preserve current lifecycle, or `draft` for a new record |
| `repair_scheduled`, `repaired` | Repair fact only; lifecycle unchanged |
| `user_reported_submitted` | `filed_by_user` |
| `user_reported_approved`, `user_reported_denied` | Decision received plus reported outcome |
| `resolved` | Requires confirmation it was resolved without filing |
| `filed_demo`, run states, unknown values | Reject; requires explicit reconciliation |

## Schema and migration

The application migration directory is **`apps/web/lib/db/migrations`**:

1. `0001_ui_baseline.sql` establishes the five existing UI tables on an empty DB
   and leaves existing tables/data in place.
2. `0002_clerk_identity_status.sql` adds the local users mirror and ownership
   references, converts lifecycle labels to codes, and adds repair/outcome fields
   with constraints. Existing IDs and historical message text/status labels remain.

The migration refuses non-Clerk owners, incompatible UUID-user schemas, unknown
statuses, ambiguous `resolved`/`filed_demo`, and existing `prepared`/`Package prepared`
records whose packet approval cannot be established. Reconcile these explicitly;
do not silently relabel them.

The old `apps/api/migrations` and `app.db.verify` describe the prototype schema.
Do not apply that migration tree to the UI DB or combine the histories. The runner
rejects incompatible migration ledgers.

After reviewing the target and setting `DATABASE_URL`, run from `apps/api`:

```sh
python -m pip install -r requirements-db.txt
python -m app.db.migrate --directory ../web/lib/db/migrations
```

Pending migrations run in one transaction with checksums and an advisory lock.
Repeating the command checks history and applies only pending files. Deploy the
updated UI/API together with this migration: old clients send display labels,
while the new API accepts codes. Only disposable synthetic databases were migrated
during this change; no application database was modified.

## Contract generation and checks

`packages/contracts/domain.json` is the shared vocabulary. From the repo root:

```sh
python3 packages/contracts/generate_domain.py
python3 packages/contracts/generate_domain.py --check
```

This generates Python types and TypeScript values/labels. HTTP changes also need
`apps/web/lib/api-spec/openapi.yaml` updated and its clients regenerated with
`pnpm --filter @workspace/api-spec run codegen` from `apps/web`. The Python OpenAPI
snapshot is `packages/contracts/openapi.json`.

Run `pnpm test` and `pnpm run typecheck` from `apps/web`. From `apps/api`, run
`pytest -q --ignore=tests/database` for agent/API tests. Migration tests require a
disposable `TEST_DATABASE_URL` ending in `_test` and a role allowed to create/drop
temporary test databases:

```sh
REQUIRE_DATABASE_TESTS=1 python -m pytest -q tests/database/test_ui_identity_status.py tests/database/test_migrations.py
```

## Next integration steps

1. Connect verified Clerk identity to the Python API principal resolver.
2. Add Python repositories over the UI schema; extend it for versioned assessments,
   approvals, artifacts, and durable runs.
3. Wire policy indexing/retrieval, UI agent actions, and evaluation adapters.

The current in-memory run/claim/approval/artifact stores still reset on restart.
