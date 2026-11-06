# Evaluation scaffold

`datasets/dev.jsonl` contains eight development scenarios. `datasets/held_out.jsonl` contains four held-out scenarios. Keep related paraphrases in the same split. All records are fictional.

`evaluators.py` provides starter deterministic field checks. Add exact code evaluators for routing, arithmetic, citation presence, approvals, version checks, persistence, idempotency, and user isolation. Use a human rubric to assess whether policy evidence actually supports an explanation.

`run_eval.py` is a scaffold: implement `run_case()` to call the same backend workflow service as the app. Record actual results and failures in Langfuse or a clearly labeled local report. Do not report an evaluation score until the workflow adapter is wired and scenarios have run.

## Langfuse experiment for the current preview

The API currently implements routing and deductible arithmetic. `langfuse_experiment.py` runs six fictional cases from `datasets/workflow_preview.jsonl` through those same functions and records exact-match scores in a Langfuse experiment. This is a small development smoke evaluation, not the full 12-scenario MVP evaluation. The existing development and held-out sets remain for the full workflow once it exists.

Install the API dependencies and export `LANGFUSE_TRACING_ENABLED=true`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL` for the intended Langfuse region. For example, from the repository root:

```sh
python -m pip install -e 'apps/api[test]'
python evals/langfuse_experiment.py --run-name preview-v1
```

Only use synthetic cases: experiment inputs and results are sent to the configured Langfuse instance. The experiment uses a local JSONL dataset; it does not create a hosted Langfuse dataset. Langfuse SDK v5 requires a compatible Langfuse server; consult the SDK compatibility documentation for self-hosted installations.
