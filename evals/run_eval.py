"""Run synthetic scenarios through the agent API and report unscored checks."""
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


def stale_approval_case(client: httpx.Client, *, policy_id: str | None,
                        claim_id: str | None) -> dict[str, Any]:
    """Probe a deliberately invalid approval only against the synthetic fixture API."""
    if not policy_id or not claim_id:
        return {"unscored_reason": "A synthetic policy and claim are required for stale approval"}
    response = client.post("/agent/runs", json={"request_key": str(uuid4()),
                           "message": "I paid $150. Prepare the packet.",
                           "policy_id": policy_id, "claim_id": claim_id})
    response.raise_for_status()
    run = response.json()
    pending = run.get("pending") or {}
    if (run.get("mode") != "fixture" or pending.get("kind") != "human_review"
            or not isinstance(pending.get("artifact_version"), int)):
        return {"unscored_reason": "Stale approval requires a pending fixture-mode review"}
    invalid = client.post(f"/agent/runs/{run['run_id']}/responses", json={
        "request_key": str(uuid4()), "interrupt_id": pending["interrupt_id"],
        "decision": {"artifact_version": pending["artifact_version"] + 1, "action": "approve"},
    })
    if invalid.status_code != 409:
        invalid.raise_for_status()
    after = client.get(f"/agent/runs/{run['run_id']}")
    after.raise_for_status()
    current = after.json()
    result = {"approval_rejected": invalid.status_code == 409, "execution_error": False}
    if current.get("status") == "awaiting_review" and current.get("action_result") is None:
        result["action_performed"] = False
    elif current.get("action_result") is not None:
        result["action_performed"] = True
    return result


def run_case(case_input: dict[str, Any], client: httpx.Client, *,
             policy_id: str | None = None, claim_id: str | None = None) -> dict[str, Any]:
    """Use the public agent endpoint with synthetic scenarios."""
    if case_input.get("action") == "approve_old_package_version":
        return stale_approval_case(client, policy_id=policy_id,
                                   claim_id=claim_id or case_input.get("claim_id"))
    if case_input.get("evaluation_fixture"):
        return {"unscored_reason": "Adversarial fixture injection is not exposed by the public API"}
    if "message" not in case_input:
        return {"unscored_reason": "Lifecycle scenario requires an integration-specific adapter"}
    selected_policy = policy_id or case_input.get("selected_policy_id")
    if not selected_policy:
        return {"unscored_reason": "No seeded policy ID is available"}
    response = client.post("/agent/runs", json={
        "request_key": str(uuid4()), "message": case_input["message"],
        "policy_id": selected_policy,
        "claim_id": claim_id or case_input.get("selected_claim_id"),
    })
    response.raise_for_status()
    run = response.json()
    pending, answer = run.get("pending") or {}, run.get("answer") or {}
    estimate = pending.get("estimate") or answer.get("estimate") or {}
    actual: dict[str, Any] = {"route": run.get("route"), "run_status": run.get("status"),
                              "execution_error": run.get("status") == "failed"}
    if run.get("status") in {"completed", "awaiting_review"} and "citations" in run:
        actual["citations"] = run["citations"]
    if pending.get("kind") == "human_review":
        actual["approval_required"] = True
        actual["confirmation_required"] = True
    if pending.get("kind") == "clarification":
        actual["must_ask_for_missing_fact"] = bool(pending.get("questions"))
    if run.get("status") == "awaiting_information":
        actual["final_status"] = "needs_info"
    if estimate.get("estimated_payment") is not None:
        actual["estimated_payment"] = estimate["estimated_payment"]
    return actual


def run_dataset(dataset: Path, client: httpx.Client, *, policy_id=None, claim_id=None) -> dict:
    records = []
    for line in dataset.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        try:
            actual = run_case(case["input"], client, policy_id=policy_id, claim_id=claim_id)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            actual = {"unscored_reason": "Workflow request failed or returned an invalid response",
                      "execution_error": True}
        checks = evaluate(case["expected"], actual)
        records.append({"id": case["id"], "actual": actual,
                        "checks": [asdict(check) for check in checks]})
    if not records:
        raise ValueError("Dataset is empty")
    checks = [check for record in records for check in record["checks"]]
    return {"cases": records,
            "error_cases": sum(r["actual"].get("execution_error") is True for r in records),
            "passed_checks": sum(c["passed"] is True for c in checks),
            "failed_checks": sum(c["passed"] is False for c in checks),
            "unscored_checks": sum(c["passed"] is None for c in checks)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--policy-id", help="ID of the seeded synthetic policy")
    parser.add_argument("--claim-id", help="Optional ID of a seeded synthetic claim")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    token = os.environ.get("EVAL_API_TOKEN")
    if not token:
        parser.error("Set EVAL_API_TOKEN for a synthetic evaluation account")
    with httpx.Client(base_url=args.base_url, timeout=180,
                      headers={"Authorization": "Bearer " + token}) as client:
        report = run_dataset(args.dataset, client, policy_id=args.policy_id, claim_id=args.claim_id)
    text = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)

if __name__ == "__main__":
    main()
