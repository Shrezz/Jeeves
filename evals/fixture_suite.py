"""Run the 12 MVP scenarios in isolated synthetic agent fixtures.

The fixture service is intentionally in-memory. Its restart check measures that
fixture's durability, not a future Postgres-backed deployment.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))

from evaluators import evaluate
from fastapi.testclient import TestClient
from run_eval import stale_approval_case

from app.agents.checkpoints import memory_checkpointer
from app.agents.graph import build_graph
from app.main import create_app
from app.schemas.agents import CoverageDraft, PacketDraft
from app.services.bootstrap import demo_auth
from app.services.fixtures import FixtureModel, FixtureStore, fixture_context
from app.services.workflow import WorkflowService

MANUAL_CASES = {"dev_01_covered_question", "dev_04_exclusion", "dev_07_unsupported_evidence"}
MANUAL_FIELDS = ("citation_support_human", "explanation_correct_human")


class OneBadCitation(FixtureModel):
    """Inject an unsupported citation once, then let the graph revise it."""

    def __init__(self, draft_type=PacketDraft):
        self.injected = False
        self.draft_type = draft_type
        self.first_citation_ids = []

    async def _generate(self, *, prompt, payload, output_type):
        result = await super()._generate(prompt=prompt, payload=payload, output_type=output_type)
        if output_type is self.draft_type and not self.injected:
            self.injected = True
            self.first_citation_ids = ["invented-citation"]
            if output_type is PacketDraft:
                coverage = result.coverage.model_copy(
                    update={"citation_ids": self.first_citation_ids}
                )
                return result.model_copy(update={"coverage": coverage})
            return result.model_copy(update={"citation_ids": self.first_citation_ids})
        return result


def make_service(store, *, generator=None):
    return WorkflowService(
        build_graph(memory_checkpointer()),
        fixture_context(store, generator=generator),
        artifacts=store,
        mode="fixture",
        model_mode="fixture",
    )


def start(client, message):
    response = client.post(
        "/agent/runs",
        json={
            "request_key": str(uuid4()),
            "message": message,
            "policy_id": "demo-policy",
            "claim_id": "demo-window",
        },
    )
    response.raise_for_status()
    return response.json()


def approve(client, run, request_key):
    pending = run.get("pending") or {}
    if pending.get("kind") != "human_review":
        raise ValueError("Scenario did not reach human review")
    body = {
        "request_key": request_key,
        "interrupt_id": pending["interrupt_id"],
        "decision": {"artifact_version": pending["artifact_version"], "action": "approve"},
    }
    return client.post(f"/agent/runs/{run['run_id']}/responses", json=body), body


def run_fixture_case(case):
    """Exercise real graph/API operations. All stores and identities are synthetic."""
    case_id = case["id"]
    store = FixtureStore.seeded()
    if case_id == "dev_05_missing_cause":
        claim = store.claims["demo-window"]
        facts = claim.facts.model_copy(update={"cause": None, "occurred_on": None})
        store.claims["demo-window"] = claim.model_copy(update={"facts": facts})
    if case_id == "dev_04_exclusion":
        claim = store.claims["demo-window"]
        store.claims["demo-window"] = claim.model_copy(
            update={"facts": claim.facts.model_copy(update={"cause": "Wear and tear"})}
        )
    if case_id == "dev_08_reviewer_correction":
        claim = store.claims["demo-window"]
        store.claims["demo-window"] = claim.model_copy(
            update={"facts": claim.facts.model_copy(update={"repair_cost": Decimal("150.00")})}
        )
    generator = OneBadCitation() if case_id == "dev_08_reviewer_correction" else None
    service = make_service(store, generator=generator)
    with TestClient(create_app(service, demo_auth("synthetic-eval-token"))) as client:
        client.headers["Authorization"] = "Bearer synthetic-eval-token"
        if case_id == "held_02_stale_approval":
            return stale_approval_case(client, policy_id="demo-policy", claim_id="demo-window")
        if case_id == "held_03_duplicate_action":
            run = start(client, "I paid $150. Prepare the packet.")
            key = str(uuid4())
            first, body = approve(client, run, key)
            first.raise_for_status()
            second = client.post(f"/agent/runs/{run['run_id']}/responses", json=body)
            second.raise_for_status()
            if first.json() != second.json():
                return {"duplicate_packet_actions": max(1, len(store.events) - 1)}
            return {"duplicate_packet_actions": max(0, len(store.events) - 1)}
        if case_id == "held_01_restart_resume":
            note = "Save the repair update. Synthetic note: repair completed."
            run = start(client, note)
            response, _ = approve(client, run, str(uuid4()))
            response.raise_for_status()
            if not store.events or note not in store.claims["demo-window"].notes:
                return {"unscored_reason": "Fixture did not save the pre-restart claim and note"}
            # Fresh in-memory service simulates process restart; it has no durable backing.
            new_store = FixtureStore.seeded()
            new_service = make_service(new_store)
            with TestClient(
                create_app(new_service, demo_auth("synthetic-eval-token"))
            ) as restarted:
                restarted.headers["Authorization"] = "Bearer synthetic-eval-token"
                resumed = restarted.get(f"/agent/runs/{run['run_id']}")
                saved_claim = new_store.claims.get("demo-window")
                return {
                    "claim_and_comments_persist": bool(
                        resumed.status_code == 200
                        and saved_claim
                        and note in saved_claim.notes
                        and new_store.events
                    )
                }
        if case_id == "held_04_user_isolation":
            run = start(client, "Is my broken window covered?")

            async def other_user(_request):
                return "another-synthetic-user"

            with TestClient(create_app(service, other_user)) as other:
                read = other.get(f"/agent/runs/{run['run_id']}")
                foreign = other.post(
                    "/agent/runs",
                    json={
                        "request_key": str(uuid4()),
                        "policy_id": "demo-policy",
                        "claim_id": "demo-window",
                        "message": "Is this covered?",
                    },
                )
                if read.status_code not in (200, 403, 404) or foreign.status_code not in (
                    200,
                    403,
                    404,
                ):
                    return {"unscored_reason": "Isolation probe returned an unexpected status"}
                if read.status_code == 200 or foreign.status_code == 200:
                    return {"access_allowed": True}
                # Policy selection was denied, but this fixture has no Postgres/pgvector
                # adapter to verify direct policy-chunk ownership at the storage layer.
                return {
                    "unscored_reason": "Foreign API access denied; pgvector chunk isolation is not integrated",
                    "foreign_api_access_denied": True,
                }
        run = start(client, case["input"]["message"])
        pending = run.get("pending") or {}
        answer = run.get("answer") or {}
        coverage = answer.get("coverage") or (pending.get("draft") or {}).get("coverage") or {}
        estimate = pending.get("estimate") or answer.get("estimate") or {}
        actual = {
            "route": run.get("route"),
            "must_avoid_filing": not store.events and run.get("action_result") is None,
        }
        if coverage:
            actual["coverage_answer"] = {
                "conclusion": coverage.get("conclusion"),
                "explanation": coverage.get("explanation"),
                "citation_ids": coverage.get("citation_ids", []),
            }
        if run.get("status") in {"completed", "awaiting_review"}:
            actual["citations"] = run.get("citations", [])
            actual["retrieval_expected_chunk"] = any(
                item.get("chunk_id") == "demo-wind" and item.get("page") == 2
                for item in actual["citations"]
            )
        if pending.get("kind") == "human_review":
            actual["approval_required"] = True
            actual["confirmation_required"] = True
        if estimate.get("estimated_payment") is not None:
            actual["estimated_payment"] = estimate["estimated_payment"]
        if pending.get("kind") == "clarification":
            actual["must_ask_for_missing_fact"] = bool(pending.get("questions"))
        if run.get("status") == "awaiting_information":
            actual["final_status"] = "needs_info"
        if case_id == "dev_04_exclusion" and coverage:
            actual["must_surface_limitation"] = (
                coverage.get("conclusion") == "likely_not_covered"
                and "wear" in coverage.get("explanation", "").lower()
            )
        if case_id == "dev_07_unsupported_evidence":
            actual["must_not_invent_coverage"] = (
                run.get("status") == "awaiting_information"
                or coverage.get("conclusion") == "unclear"
            )
        if case_id == "dev_08_reviewer_correction":
            state = service.runs[run["run_id"]].state
            revisions = state.get("revision_count", 0)
            ids = coverage.get("citation_ids", [])
            actual["reviewer_must_flag_unsupported_citation"] = (
                generator.injected
                and revisions == 1
                and "invented-citation" not in ids
                and bool(ids)
                and run.get("status") == "awaiting_review"
            )
            actual["max_revisions"] = revisions
        return actual


def load_cases(path):
    cases = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if not cases:
        raise ValueError("Dataset is empty")
    return cases


def reviewer_comparison():
    """Compare each injected draft before review with its graph result after review.

    The unsafe draft is inspected locally, never published or approved. This is
    a fixture comparison of citation references, not a model-quality benchmark.
    """
    comparisons = []
    for label, draft_type, message in (
        ("coverage", CoverageDraft, "Is my broken window covered?"),
        ("packet", PacketDraft, "I paid $150. Prepare the packet."),
    ):
        store = FixtureStore.seeded()
        model = OneBadCitation(draft_type)
        service = make_service(store, generator=model)
        with TestClient(create_app(service, demo_auth("synthetic-eval-token"))) as client:
            client.headers["Authorization"] = "Bearer synthetic-eval-token"
            try:
                run = start(client, message)
                answer = run.get("answer") or {}
                pending = run.get("pending") or {}
                coverage = (
                    answer.get("coverage") or (pending.get("draft") or {}).get("coverage") or {}
                )
                ids = coverage.get("citation_ids", [])
                state = service.runs[run["run_id"]].state
                comparisons.append(
                    {
                        "case": label,
                        "before_review_citation_valid": bool(model.first_citation_ids)
                        and set(model.first_citation_ids) <= {"demo-wind"},
                        "after_review_citation_valid": bool(ids) and set(ids) <= {"demo-wind"},
                        "revision_count": state.get("revision_count", 0),
                        "status": run.get("status"),
                    }
                )
            except Exception as exc:  # noqa: BLE001 - report each case failure without terminating the run
                comparisons.append({"case": label, "execution_error": type(exc).__name__})
    return comparisons


def run_one(case, annotations=None):
    started = perf_counter()
    try:
        actual = run_fixture_case(case)
    except Exception as exc:  # noqa: BLE001 - report each case failure without terminating the run
        actual = {
            "execution_error": True,
            "unscored_reason": f"Scenario failed: {type(exc).__name__}",
        }
    expected = dict(case["expected"])
    if case["id"] in MANUAL_CASES:
        for field in MANUAL_FIELDS:
            expected[field] = True
            value = (annotations or {}).get(case["id"], {}).get(field)
            if isinstance(value, bool):
                actual[field] = value
    return {
        "id": case["id"],
        "actual": actual,
        "checks": [asdict(check) for check in evaluate(expected, actual)],
        "latency_ms": round((perf_counter() - started) * 1000, 2),
    }


def report(cases, annotations=None):
    records = [run_one(case, annotations) for case in cases]
    checks = [check for record in records for check in record["checks"]]
    metrics = {}
    for check in checks:
        metric = metrics.setdefault(check["name"], {"passed": 0, "failed": 0, "unscored": 0})
        outcome = (
            "passed"
            if check["passed"] is True
            else "failed"
            if check["passed"] is False
            else "unscored"
        )
        metric[outcome] += 1
    for metric in metrics.values():
        measured = metric["passed"] + metric["failed"]
        metric["pass_rate"] = metric["passed"] / measured if measured else None
    case_outcomes = {"passed": 0, "failed": 0, "unscored": 0}
    for record in records:
        values = [item["passed"] for item in record["checks"]]
        outcome = (
            "failed"
            if False in values or record["actual"].get("execution_error")
            else "unscored"
            if None in values
            else "passed"
        )
        case_outcomes[outcome] += 1
    return {
        "mode": "synthetic_in_memory_fixture",
        "cases": records,
        "reviewer_comparison": reviewer_comparison()
        if any(case["id"] == "dev_08_reviewer_correction" for case in cases)
        else [],
        "metrics": metrics,
        "end_to_end_cases": case_outcomes,
        "mean_latency_ms": round(sum(r["latency_ms"] for r in records) / len(records), 2),
        "passed_checks": sum(c["passed"] is True for c in checks),
        "failed_checks": sum(c["passed"] is False for c in checks),
        "unscored_checks": sum(c["passed"] is None for c in checks),
        "execution_errors": sum(r["actual"].get("execution_error") is True for r in records),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--annotations", type=Path, help="Optional human-reviewed JSON boolean labels"
    )
    parser.add_argument(
        "--langfuse", action="store_true", help="Send a separate run using synthetic cases only"
    )
    parser.add_argument("--run-name", default="fixture-suite")
    parser.add_argument(
        "--strict", action="store_true", help="Exit nonzero on failed, unscored, or errored checks"
    )
    args = parser.parse_args()
    cases = load_cases(args.dataset)
    annotations = (
        json.loads(args.annotations.read_text(encoding="utf-8")) if args.annotations else {}
    )
    if not isinstance(annotations, dict):
        parser.error("Annotations must be a JSON object keyed by case ID")
    for case_id, labels in annotations.items():
        if (
            case_id not in MANUAL_CASES
            or not isinstance(labels, dict)
            or any(
                field not in MANUAL_FIELDS or not isinstance(value, bool)
                for field, value in labels.items()
            )
        ):
            parser.error(f"Invalid human-review labels for {case_id}")
    result = report(cases, annotations)
    encoded = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    if args.langfuse:
        if (
            os.getenv("LANGFUSE_TRACING_ENABLED", "false").lower() != "true"
            or not os.getenv("LANGFUSE_PUBLIC_KEY")
            or not os.getenv("LANGFUSE_SECRET_KEY")
        ):
            parser.error("Set LANGFUSE_TRACING_ENABLED=true and both Langfuse keys")
        from langfuse import Evaluation, get_client

        data = []
        for case in cases:
            expected = dict(case["expected"])
            if case["id"] in MANUAL_CASES:
                expected.update({field: True for field in MANUAL_FIELDS})
            data.append(
                {
                    "input": {"id": case["id"], "input": case["input"]},
                    "expected_output": expected,
                    "metadata": {"case_id": case["id"]},
                }
            )

        def task(*, item, **kwargs):
            case = item["input"]
            try:
                actual = run_fixture_case(case)
            except Exception as exc:  # noqa: BLE001 - report each case failure without terminating the run
                actual = {
                    "execution_error": True,
                    "unscored_reason": f"Scenario failed: {type(exc).__name__}",
                }
            for field in MANUAL_FIELDS:
                value = annotations.get(case["id"], {}).get(field)
                if isinstance(value, bool):
                    actual[field] = value
            return actual

        def score(*, output, expected_output, **kwargs):
            checks = evaluate(expected_output, output)
            values = [
                Evaluation(name=f"check_{c.name}", value=float(c.passed))
                for c in checks
                if c.passed is not None
            ]
            values.append(
                Evaluation(name="unscored_checks", value=sum(c.passed is None for c in checks))
            )
            values.append(
                Evaluation(
                    name="execution_error", value=float(output.get("execution_error") is True)
                )
            )
            return values

        client = get_client()
        try:
            experiment = client.run_experiment(
                name="claim-companion-fixture",
                run_name=args.run_name,
                data=data,
                task=task,
                evaluators=[score],
                max_concurrency=1,
            )
            print(experiment.format())
        finally:
            client.flush()
    if args.strict and (
        result["failed_checks"] or result["unscored_checks"] or result["execution_errors"]
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
