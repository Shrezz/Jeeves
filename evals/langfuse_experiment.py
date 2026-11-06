"""Run synthetic preview scenarios through the existing backend functions."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.agents.workflow import estimate_payment, route_message


def run_task(*, item, **kwargs):
    case = item["input"]
    if case["kind"] == "route":
        result = route_message(case["message"], selected_claim_id=case.get("selected_claim_id"))
        return {"intent": result.intent, "needs_clarification": result.needs_clarification}
    if case["kind"] == "estimate":
        return {"estimated_payment": str(estimate_payment(case["eligible_loss"], case["deductible"]))}
    raise ValueError(f"Unsupported scenario kind: {case['kind']}")


def score_output(*, output, expected_output, **kwargs):
    from langfuse import Evaluation
    return Evaluation(name="expected_fields", value=float(output == expected_output))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path(__file__).parent / "datasets/workflow_preview.jsonl")
    parser.add_argument("--run-name", default="workflow-preview")
    args = parser.parse_args()
    if not os.getenv("LANGFUSE_PUBLIC_KEY") or not os.getenv("LANGFUSE_SECRET_KEY"):
        parser.error("Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY before running an experiment")
    if os.getenv("LANGFUSE_TRACING_ENABLED", "false").lower() != "true":
        parser.error("Set LANGFUSE_TRACING_ENABLED=true to send experiment traces")
    from langfuse import get_client
    data = [json.loads(line) for line in args.dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not data:
        parser.error("Dataset is empty")
    client = get_client()
    try:
        result = client.run_experiment(name="claim-companion-preview", run_name=args.run_name,
                                       data=data, task=run_task, evaluators=[score_output])
        print(result.format())
    finally:
        client.flush()


if __name__ == "__main__":
    main()
