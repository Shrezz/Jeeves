"""Run a synthetic workflow dataset through the agent API and Langfuse."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import httpx
from evaluators import evaluate
from langfuse import Evaluation, get_client
from run_eval import run_case


def score_checks(*, output, expected_output, **kwargs):
    checks = evaluate(expected_output, output)
    scores = [
        Evaluation(name=f"check_{check.name}", value=float(check.passed))
        for check in checks
        if check.passed is not None
    ]
    scores.append(Evaluation(name="unscored_checks", value=sum(c.passed is None for c in checks)))
    if "execution_error" in output:
        scores.append(Evaluation(name="execution_error", value=float(output["execution_error"])))
    return scores


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--policy-id", help="ID of the seeded synthetic policy")
    parser.add_argument("--claim-id", help="ID of the seeded synthetic claim")
    parser.add_argument("--run-name", default="workflow-evaluation")
    args = parser.parse_args()
    token = os.getenv("EVAL_API_TOKEN")
    if not token or not os.getenv("LANGFUSE_PUBLIC_KEY") or not os.getenv("LANGFUSE_SECRET_KEY"):
        parser.error("Set EVAL_API_TOKEN, LANGFUSE_PUBLIC_KEY, and LANGFUSE_SECRET_KEY")
    if os.getenv("LANGFUSE_TRACING_ENABLED", "false").lower() != "true":
        parser.error("Set LANGFUSE_TRACING_ENABLED=true")
    cases = [
        json.loads(line)
        for line in args.dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not cases:
        parser.error("Dataset is empty")
    data = [
        {
            "input": case["input"],
            "expected_output": case["expected"],
            "metadata": {"case_id": case["id"]},
        }
        for case in cases
    ]
    client = get_client()
    try:
        with httpx.Client(
            base_url=args.base_url, timeout=180, headers={"Authorization": "Bearer " + token}
        ) as api:

            def task(*, item, **kwargs):
                try:
                    return run_case(
                        item["input"], api, policy_id=args.policy_id, claim_id=args.claim_id
                    )
                except (httpx.HTTPError, ValueError, KeyError, TypeError):
                    return {
                        "unscored_reason": "Workflow request failed or returned an invalid response",
                        "execution_error": True,
                    }

            result = client.run_experiment(
                name="claim-companion-workflow",
                run_name=args.run_name,
                data=data,
                task=task,
                evaluators=[score_checks],
                max_concurrency=1,
            )
            print(result.format())
    finally:
        client.flush()


if __name__ == "__main__":
    main()
