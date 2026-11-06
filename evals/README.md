# Evaluation scaffold

`datasets/dev.jsonl` contains eight development scenarios. `datasets/held_out.jsonl` contains four held-out scenarios. Keep related paraphrases in the same split. All records are fictional.

`evaluators.py` provides starter deterministic field checks. Add exact code evaluators for routing, arithmetic, citation presence, approvals, version checks, persistence, idempotency, and user isolation. Use a human rubric to assess whether policy evidence actually supports an explanation.

`run_eval.py` now calls the same public API used by the UI. With the backend running,
set `EVAL_API_TOKEN` to its bearer token in your environment, then from the repo root:

```bash
apps/api/.venv/bin/python evals/run_eval.py evals/datasets/dev.jsonl \
  --policy-id demo-policy --claim-id demo-window --output reports/dev-api.json
```

The optional ID arguments map old dataset selections to the seeded demo. They also change
the available claim context, so fixture results are only integration checks. Real evaluations
must seed scenario-specific facts/policies and use real models. Do not tune on held-out cases.

The report distinguishes data `mode` and `model_mode`. Missing semantic measurements are
`passed: null` and excluded from measured totals. Adversarial fixture injection is explicitly
unscored by this HTTP runner; the Python graph tests exercise fabricated citations and
bounded refinement. A human rubric is still needed for factual support/grounding. No
LangSmith experiment or live model-quality score is implied by these offline checks.

## Langfuse experiment for the current preview

The read-only preview endpoints implement deterministic routing and deductible arithmetic alongside the full agent API. `langfuse_experiment.py` runs six fictional cases from `datasets/workflow_preview.jsonl` through those same functions and records exact-match scores in a Langfuse experiment. This is a small development smoke evaluation, not the full 12-scenario MVP evaluation. Use the API runner above for the existing development and held-out workflow sets.

Install the API dependencies and export `LANGFUSE_TRACING_ENABLED=true`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL` for the intended Langfuse region. For example, from the repository root:

```sh
python -m pip install -e 'apps/api[test]'
python evals/langfuse_experiment.py --run-name preview-v1
```

Only use synthetic cases: experiment inputs and results are sent to the configured Langfuse instance. The experiment uses a local JSONL dataset; it does not create a hosted Langfuse dataset. Langfuse SDK v5 requires a compatible Langfuse server; consult the SDK compatibility documentation for self-hosted installations.
