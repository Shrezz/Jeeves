# Evaluation scaffold

`datasets/dev.jsonl` contains eight development scenarios. `datasets/held_out.jsonl` contains four held-out scenarios. Keep related paraphrases in the same split. All records are fictional.

`evaluators.py` provides starter deterministic field checks. Add exact code evaluators for routing, arithmetic, citation presence, approvals, version checks, persistence, idempotency, and user isolation. Use a human rubric to assess whether policy evidence actually supports an explanation.

`run_eval.py` is a scaffold: implement `run_case()` to call the same backend workflow service as the app. Record actual results and failures in Langfuse or a clearly labeled local report. Do not report an evaluation score until the workflow adapter is wired and scenarios have run.
