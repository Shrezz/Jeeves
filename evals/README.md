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

Reports include each case and check, passed/failed/unscored counts, per-check rates, end-to-end counts, elapsed time, and a two-case comparison of the injected draft before review and the result after review. The comparison examines citation references, not semantic correctness or live-model quality. The fixture model is deterministic; it does not establish real LLM accuracy. See `results/` for the recorded sample run and its failures.

Add `--strict` to exit nonzero if any check fails, is unscored, or the scenario errors. This is suitable for a CI gate once the team has supplied the required human annotations and connected the missing integrations.

## Human review

Follow `review-rubric.md` after inspecting the generated synthetic answers and supporting policy passages. Optional JSON annotations are supplied with `--annotations PATH`. Missing human labels are always reported as unscored, never as passes. Automated citation presence or reviewer agreement does not establish that an explanation is supported.

## Send an experiment to Langfuse

Export `LANGFUSE_TRACING_ENABLED=true`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and the correct `LANGFUSE_BASE_URL`. For a local-data experiment:

```sh
apps/api/.venv/bin/python evals/fixture_suite.py evals/datasets/dev.jsonl --langfuse --run-name fixture-dev-v1
apps/api/.venv/bin/python evals/fixture_suite.py evals/datasets/held_out.jsonl --langfuse --run-name fixture-held-out-v1
```

These experiments send the synthetic inputs, outputs, and measured scores to the configured Langfuse project; `unscored_checks` is recorded separately. They do not create a hosted Langfuse dataset. Model token usage is available only when the provider returns it; cost depends on Langfuse model pricing. Never put real credentials or real policyholder data in scenarios.

## Run against an integrated API

Set `EVAL_API_TOKEN` for a dedicated synthetic account. The runner maps the scenario IDs to a seeded synthetic policy and claim:

```sh
apps/api/.venv/bin/python evals/run_eval.py evals/datasets/dev.jsonl --policy-id demo-policy --claim-id demo-window --output reports/dev-api.json
apps/api/.venv/bin/python evals/langfuse_workflow_experiment.py evals/datasets/dev.jsonl --policy-id demo-policy --claim-id demo-window --run-name dev-api-v1
```

The HTTP runner reports unmeasured checks and request errors separately. Its stale-approval probe sends an edit and an invalid approval only when the server reports fixture mode. Other lifecycle and adversarial scenarios require dedicated integration adapters; they are not silently counted as successes. Use a dedicated synthetic environment because starting runs may save drafts.

The in-memory fixture lacks durable Postgres claims/checkpoints, a real vector store, and a real embedding provider. Full restart, storage-level isolation, and end-to-end model-quality claims require those integrations, a reviewed dataset, and an actual Langfuse run with the team's credentials.
