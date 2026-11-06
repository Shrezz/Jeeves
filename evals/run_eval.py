"""Evaluate the public API; absent semantic/fixture measurements are explicitly unscored."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from evaluators import evaluate


def run_case(
    case_input: dict[str, Any],
    client: httpx.Client,
    *,
    policy_id: str | None = None,
    claim_id: str | None = None,
) -> dict[str, Any]:
    if case_input.get("evaluation_fixture"):
        return {
            "unscored_reason": "Adversarial fixture injection belongs in Python workflow tests."
        }
    response = client.post(
        "/agent/runs",
        json={
            "request_key": str(uuid4()),
            "message": case_input["message"],
            "policy_id": policy_id or case_input["selected_policy_id"],
            "claim_id": claim_id or case_input.get("selected_claim_id"),
        },
    )
    response.raise_for_status()
    run = response.json()
    pending, answer = run.get("pending") or {}, run.get("answer") or {}
    estimate = pending.get("estimate") or answer.get("estimate") or {}
    actual = {
        "route": run["route"],
        "citations": run["citations"],
        "run_id": run["run_id"],
        "mode": run["mode"],
        "model_mode": run.get("model_mode", "unknown"),
        "approval_required": pending.get("kind") == "human_review",
        "confirmation_required": pending.get("kind") == "human_review",
        "must_ask_for_missing_fact": pending.get("kind") == "clarification"
        and bool(pending.get("questions")),
        "final_status": "needs_info"
        if run["status"] == "awaiting_information"
        else run["status"],
        "must_avoid_filing": run["action_result"] is None,
    }
    if estimate.get("estimated_payment") is not None:
        actual["estimated_payment"] = float(estimate["estimated_payment"])
    return actual


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--policy-id", help="Optional mapping to a seeded policy ID")
    parser.add_argument("--claim-id", help="Optional mapping to a seeded claim ID")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    token = os.environ.get("EVAL_API_TOKEN")
    if not token:
        parser.error("Set EVAL_API_TOKEN in the environment")
    records = []
    with httpx.Client(
        base_url=args.base_url,
        timeout=180,
        headers={"Authorization": "Bearer " + token},
    ) as client:
        for line in args.dataset.read_text().splitlines():
            if not line.strip():
                continue
            case = json.loads(line)
            actual = run_case(
                case["input"], client, policy_id=args.policy_id, claim_id=args.claim_id
            )
            checks = (
                []
                if actual.get("unscored_reason")
                else evaluate(case["expected"], actual)
            )
            records.append(
                {
                    "id": case["id"],
                    "actual": actual,
                    "checks": [asdict(check) for check in checks],
                }
            )
    measured = [c for r in records for c in r["checks"] if c["passed"] is not None]
    report = {
        "note": "Fixture mode measures wiring only. Semantic grounding needs a human rubric.",
        "measured_checks": len(measured),
        "passed_checks": sum(c["passed"] for c in measured),
        "cases": records,
    }
    encoded = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n")
    print(encoded)


if __name__ == "__main__":
    main()
