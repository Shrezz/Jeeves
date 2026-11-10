# Claim Companion evaluations

The requirements define eight development scenarios and four held-out scenarios. The JSONL files are fictional starter labels; the team must review them against the chosen policy and expected behavior before treating them as a golden dataset. Do not tune on the held-out cases.

## Run the complete fixture suite locally

From the repository root, install the API dependencies and run:

```sh
cd apps/api && uv sync --locked --group dev && cd ../..
apps/api/.venv/bin/python evals/fixture_suite.py evals/datasets/dev.jsonl --output reports/fixture-dev.json
apps/api/.venv/bin/python evals/fixture_suite.py evals/datasets/held_out.jsonl --output reports/fixture-held-out.json
```

Each scenario starts a separate in-memory synthetic agent service and uses the same API and graph as the demo. The suite includes a controlled bad-citation injection, one refinement, a stale approval, duplicate approval replay, a restart probe, and cross-user API access. Approvals are simulated only inside the isolated fixture. The restart probe recreates the in-memory service and is expected to expose its lack of durable state; it does not test the separate Postgres schema. The isolation probe checks the API boundary; direct pgvector chunk isolation remains unscored until its adapter is connected.

For Python statement and branch coverage, run `uv run --locked pytest --cov=app --cov-branch --cov-report=term-missing` from `apps/api`. Skipped PostgreSQL tests are excluded from executed coverage and must be run separately with the disposable database described in `docs/database.md`.

The `API tests and coverage` GitHub workflow runs the API suite and retains a coverage artifact on relevant pushes and pull requests. Database tests run in the separate PostgreSQL workflow; neither workflow measures the standalone `RAG/policy_rag` package.

Reports include each case and check, passed/failed/unscored counts, per-check rates, end-to-end counts, elapsed time, and a two-case comparison of the injected draft before review and the result after review. The comparison examines citation references, not semantic correctness or live-model quality. The fixture model is deterministic; it does not establish real LLM accuracy. See `results/` for the recorded sample run and its failures.

Add `--strict` to exit nonzero if any check fails, is unscored, or the scenario errors. This is suitable for a CI gate once the team has supplied the required human annotations and connected the missing integrations.
`--fail-on-failed` fails on measured failures or execution errors while keeping
missing human labels unscored. CI uses it for development scenarios only; it does
not treat missing labels as passes or run the held-out split for tuning.

## Human review

Follow `review-rubric.md` after inspecting the generated synthetic answers and supporting policy passages. Optional JSON annotations are supplied with `--annotations PATH`. Missing human labels are always reported as unscored, never as passes. Automated citation presence or reviewer agreement does not establish that an explanation is supported.

## Local policy RAG and embeddings

Install `RAG/requirements.txt` in `RAG/.venv`, then from the repository root run:

```sh
RAG/.venv/bin/python evals/rag_suite.py --strict --output reports/rag-dev.json
RAG/.venv/bin/python evals/rag_suite.py --dataset evals/datasets/rag_held_out.jsonl --strict --output reports/rag-held-out.json
```

The suite uses the actual PDF parser, chunker, MiniLM embeddings and a disposable
Chroma index; it never reads the application's policy database. Fifteen development
scenarios include thirteen expected-passage queries and two unsupported-topic checks;
three held-out queries check expected passages. Reports include rank, recall at the returned
result count, mean reciprocal rank, page checks, timing and errors. It checks
indexing repeatability, embedding dimensions/finite values/repeatability, three
synthetic relative-similarity probes, and owner/policy isolation. These synthetic
labels need team review. Citation checks verify that the cited words appear in order
on the cited source page, allowing for omitted PDF decorations. This does not prove
semantic faithfulness. Unsupported-topic checks measure only source and retrieval
content; the generated answer's abstention and human review remain unscored. Held-out
queries should not be used for tuning.

Add `--langfuse --run-name NAME` with Langfuse environment variables set to export
the fictional query and component-check scores. Langfuse export is restricted to the
two supplied dataset paths; keep those files fictional. `--strict` gates measured failures
and execution errors, not the explicitly unscored human-review criteria. The first
run downloads MiniLM to the temporary evaluation directory. Search-only scores do
not evaluate a generated response or the signed-in UI end to end.

## Send an experiment to Langfuse

Export `LANGFUSE_TRACING_ENABLED=true`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and the correct `LANGFUSE_BASE_URL`. For a local-data experiment:

```sh
apps/api/.venv/bin/python evals/fixture_suite.py evals/datasets/dev.jsonl --langfuse --run-name fixture-dev-v1
apps/api/.venv/bin/python evals/fixture_suite.py evals/datasets/held_out.jsonl --langfuse --run-name fixture-held-out-v1
```

These experiments send the synthetic inputs, outputs, and measured scores to the configured Langfuse project; `unscored_checks` is recorded separately. They do not create a hosted Langfuse dataset. Model token usage is available only when the provider returns it; cost depends on Langfuse model pricing. Never put real credentials or real policyholder data in scenarios.

The separate `langfuse_experiment.py` and `datasets/workflow_preview.jsonl` exercise the read-only router and deductible functions with six synthetic smoke cases. They are useful for preview checks and do not replace the 12-scenario workflow suite.

## Run against an integrated API

Set `EVAL_API_TOKEN` for a dedicated synthetic account. The runner maps the scenario IDs to a seeded synthetic policy and claim:

```sh
apps/api/.venv/bin/python evals/run_eval.py evals/datasets/dev.jsonl --policy-id demo-policy --claim-id demo-window --output reports/dev-api.json
apps/api/.venv/bin/python evals/langfuse_workflow_experiment.py evals/datasets/dev.jsonl --policy-id demo-policy --claim-id demo-window --run-name dev-api-v1
```

The HTTP runner reports unmeasured checks and request errors separately. Its stale-approval probe sends an edit and an invalid approval only when the server reports fixture mode. Other lifecycle and adversarial scenarios require dedicated integration adapters; they are not silently counted as successes. Use a dedicated synthetic environment because starting runs may save drafts.

The in-memory fixture lacks durable Postgres claims/checkpoints, a real vector store, and a real embedding provider. Full restart, storage-level isolation, and end-to-end model-quality claims require those integrations, a reviewed dataset, and an actual Langfuse run with the team's credentials.

## Evaluate an existing signed-in UI run

`ui_workflow_eval.py` scores an **existing** fictional claim-guidance run; it
does not start a run or call a model. The checked-in `datasets/ui_dev.jsonl`
contains three checks for the synthetic $650 window scenario: the coverage
answer, a packet, and a packet after a pending-repair clarification. These are
additional UI-specific development checks, not held-out test data.

The read-only database adapter requires the claim ID to be in
`JEEVES_SYNTHETIC_TRACE_CLAIM_IDS`, and checks that the uploaded policy PDF is
byte-for-byte identical to `data/fixtures/Cedar-Cove-Synthetic-Homeowners.pdf`.
It verifies cited excerpt text and page numbers against that PDF, plus routing,
workflow phase, expected terms, search status, conditional payment, and review
state when the chosen case calls for them. It cannot prove a citation entails a
claim or that every generated statement is correct. Those two human-review
checks remain **unscored** unless supplied for the exact run ID, artifact version,
and result fingerprint in an annotation file following `review-rubric.md`.

With the local demo database running, set `UI_EVAL_DATABASE_URL` to the local
database URL from `docs/local-development.md`, and load the synthetic claim
allowlist in your shell. Then from the repository root:

```sh
apps/api/.venv/bin/python evals/ui_workflow_eval.py \
  --run-id RUN_UUID --case-id ui_below_deductible_answer \
  --output reports/ui-answer.json
```

Add `--langfuse` and the normal Langfuse credentials to attach measured scores
only when the latest completed root matches the saved route, phase, artifact
version, and result fingerprint. The synchronous exporter runs in an isolated
process with a 45-second total limit (`--export-timeout 1..120`). Export failure,
partial acceptance, timeout, or unverified readback always makes the CLI exit
nonzero. A timeout means delivery is unknown; inspect Langfuse before retrying.
No raw prompt or policy text is uploaded by this evaluator.

Scores inherit the trace's environment and UTC start date. Their identities bind
the trace, metric, evaluator implementation SHA256 and complete case SHA256.
Retries of the same evaluation reuse IDs; a changed evaluator or case is a new
version. Readback checks metric name/type/value, environment, UTC date, trace
subject, artifact binding and evaluator/case provenance. Pagination limits fail
closed. Partial batches are reported without automatic replay.

Add `--fail-on-failed` for a nonzero exit on measured failures, or `--strict` to
also fail on unscored checks. Obtain `artifact_version` and `result_fingerprint`
from the local evaluation report, inspect that exact saved artifact, then record
only the human labels actually reviewed:

```json
{
  "RUN_UUID": {
    "artifact_version": 1,
    "result_fingerprint": "COPY_THE_64_HEX_DIGEST_FROM_THE_REPORT",
    "labels": {"citation_support_human": true}
  }
}
```

Legacy run-only annotations and labels for a different artifact are rejected.
Omitted human labels remain unscored. Reports default to `reports/`, which should
not be committed. The `Jeeves Operations` quality widgets select the current
`jeeves-ui-v2` evaluator implementation; rerun `evals/monitoring/provision_dashboard.py`
after evaluator changes. Historical versions remain available on their traces.
