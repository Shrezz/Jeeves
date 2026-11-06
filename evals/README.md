# Evaluation scaffold

`datasets/dev.jsonl` contains eight development scenarios. `datasets/held_out.jsonl` contains four held-out scenarios. Keep related paraphrases in the same split. All records are fictional.

`run_eval.py` can call the agent branch's `/agent/runs` API with a seeded synthetic policy and an evaluation account. It reports passed, failed, unscored, and execution-error counts separately. Checks that require lifecycle operations, adversarial fixture injection, audit evidence, or human review are currently unscored; a missing field is never counted as a pass. The current branch does not yet serve `/agent/runs` and must be integrated with that agent workflow first.

For an integrated app, set `EVAL_API_TOKEN` and run:

```sh
python evals/run_eval.py evals/datasets/dev.jsonl --policy-id YOUR_SYNTHETIC_POLICY_ID --claim-id YOUR_SYNTHETIC_CLAIM_ID --output reports/dev.json
python evals/run_eval.py evals/datasets/held_out.jsonl --policy-id YOUR_SYNTHETIC_POLICY_ID --claim-id YOUR_SYNTHETIC_CLAIM_ID --output reports/held-out.json
```

Use a dedicated synthetic environment; starting agent runs may persist drafts. The stale-approval scenario submits a deliberately invalid approval only after the API identifies the run as fixture mode and is awaiting review; all other scenarios leave approvals untouched. Before treating the results as a golden evaluation, the team must review the policy fixture and labels, add the remaining lifecycle/adversarial adapters and an evidence-support human rubric, and inspect failed and unscored cases.

## Langfuse experiment for the current preview

The API currently implements routing and deductible arithmetic. `langfuse_experiment.py` runs six fictional cases from `datasets/workflow_preview.jsonl` through those same functions and records exact-match scores in a Langfuse experiment. This is a small development smoke evaluation, not the full 12-scenario MVP evaluation. The existing development and held-out sets remain for the full workflow once it exists.

Install the API dependencies and export `LANGFUSE_TRACING_ENABLED=true`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL` for the intended Langfuse region. For example, from the repository root:

```sh
python -m pip install -e 'apps/api[test]'
python evals/langfuse_experiment.py --run-name preview-v1
```

Only use synthetic cases: experiment inputs and results are sent to the configured Langfuse instance. The experiment uses a local JSONL dataset; it does not create a hosted Langfuse dataset. Langfuse SDK v5 requires a compatible Langfuse server; consult the SDK compatibility documentation for self-hosted installations.

To run the development or held-out set against the integrated agent API and send measured checks to Langfuse, export `EVAL_API_TOKEN` as well as the Langfuse variables and run:

```sh
python evals/langfuse_workflow_experiment.py evals/datasets/dev.jsonl --policy-id YOUR_SYNTHETIC_POLICY_ID --claim-id YOUR_SYNTHETIC_CLAIM_ID --run-name dev-v1
python evals/langfuse_workflow_experiment.py evals/datasets/held_out.jsonl --policy-id YOUR_SYNTHETIC_POLICY_ID --claim-id YOUR_SYNTHETIC_CLAIM_ID --run-name held-out-v1
```

Each measured field produces a score; `unscored_checks` records missing measurements separately and `execution_error` identifies failed API calls. Langfuse receives synthetic dataset inputs and results, never the API token. Token usage and model cost require instrumentation from the actual model provider; the preview does not make LLM calls.
