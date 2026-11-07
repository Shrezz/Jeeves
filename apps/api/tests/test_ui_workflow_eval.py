"""Evaluate stored fictional UI outputs without a model or a live Langfuse account."""

import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "evals"))

from evaluators import Check
from ui_workflow_eval import evaluate_ui, load_case, publish_scores, source_integrity

PDF = (ROOT / "data/fixtures/Cedar-Cove-Synthetic-Homeowners.pdf").read_bytes()
POLICY = "fictional-policy"
SOURCES = [
    {
        "chunkId": POLICY + ":0",
        "page": 1,
        "excerpt": "Flat deductible $1,000 per covered occurrence",
    },
    {
        "chunkId": POLICY + ":2",
        "page": 2,
        "excerpt": "Sudden impact from windborne debris that breaks an exterior dwelling window is a covered cause of loss.",
    },
]


def checks_by_name(checks):
    return {check.name: check for check in checks}


def test_citations_are_verified_against_the_actual_policy_page_and_identity():
    assert source_integrity(SOURCES, POLICY, PDF) is True
    assert source_integrity([{**SOURCES[0], "page": 2}], POLICY, PDF) is False
    assert (
        source_integrity([{**SOURCES[0], "excerpt": "Flat deductible $10"}], POLICY, PDF) is False
    )
    assert source_integrity([{**SOURCES[0], "chunkId": "other-policy:0"}], POLICY, PDF) is False
    assert source_integrity([], POLICY, PDF) is False


def test_ui_answer_checks_do_not_pretend_keywords_prove_semantic_support():
    case = load_case(ROOT / "evals/datasets/ui_dev.jsonl", "ui_below_deductible_answer")
    observed = {
        "state": "ready",
        "policy_id": POLICY,
        "sources": SOURCES,
        "content": "If fully eligible, the $650 repair is below the $1,000 deductible, so the insurer pays $0.",
        "workflow": {
            "route": "answer_claim",
            "phase": "answer_ready",
            "publicWebSearch": {"status": "ok"},
        },
    }
    checks = checks_by_name(evaluate_ui(case, observed, PDF))
    assert checks["citation_excerpt_matches_policy_page"].passed is True
    assert checks["answer_expected_terms_present"].passed is True
    assert checks["conditional_language_present"].passed is True
    assert checks["citation_support_human"].passed is None
    assert checks["explanation_correct_human"].passed is None
    annotated = checks_by_name(evaluate_ui(case, observed, PDF, {"citation_support_human": False}))
    assert annotated["citation_support_human"].passed is False


def test_blocked_packet_fails_review_gate_and_does_not_score_missing_payment_as_zero():
    case = load_case(ROOT / "evals/datasets/ui_dev.jsonl", "ui_below_deductible_packet_clarified")
    observed = {
        "state": "ready",
        "policy_id": POLICY,
        "sources": [],
        "content": "Blocked",
        "workflow": {"route": "file_claim", "phase": "blocked", "fields": []},
    }
    checks = checks_by_name(evaluate_ui(case, observed, PDF))
    assert checks["phase"].passed is False
    assert checks["human_review_required"].passed is False
    assert checks["citations_present"].passed is False
    assert checks["conditional_payment_amount"].passed is None
    assert checks["repair_status"].passed is None


def test_missing_clarification_and_payment_in_reviewable_packet_are_visible():
    case = load_case(ROOT / "evals/datasets/ui_dev.jsonl", "ui_below_deductible_packet_clarified")
    observed = {
        "state": "ready",
        "policy_id": POLICY,
        "sources": SOURCES,
        "content": "For review",
        "workflow": {
            "route": "file_claim",
            "phase": "human_review",
            "interruptId": "i",
            "fields": [],
        },
    }
    checks = checks_by_name(evaluate_ui(case, observed, PDF))
    assert checks["human_review_required"].passed is True
    assert checks["payment_displayed"].passed is False
    assert checks["conditional_payment_amount"].passed is None
    assert checks["repair_status"].passed is False


def test_nonfinite_payment_is_failed_not_unscored():
    case = load_case(ROOT / "evals/datasets/ui_dev.jsonl", "ui_below_deductible_packet")
    observed = {
        "state": "ready",
        "policy_id": POLICY,
        "sources": SOURCES,
        "content": "For review",
        "workflow": {
            "route": "file_claim",
            "phase": "human_review",
            "interruptId": "i",
            "fields": [{"label": "Estimated payment (conditional)", "value": "NaN"}],
        },
    }
    checks = checks_by_name(evaluate_ui(case, observed, PDF))
    assert checks["conditional_payment_amount"].passed is False
    assert checks["payment_basis_displayed"].passed is False


def test_conditional_payment_and_repair_status_are_scored_when_present():
    case = load_case(ROOT / "evals/datasets/ui_dev.jsonl", "ui_below_deductible_packet_clarified")
    observed = {
        "state": "ready",
        "policy_id": POLICY,
        "sources": SOURCES,
        "content": "For review",
        "workflow": {
            "route": "file_claim",
            "phase": "human_review",
            "interruptId": "i",
            "fields": [
                {"label": "Illustrative payment if fully eligible", "value": "$0.00"},
                {"label": "Illustration basis", "value": "Assumes eligibility."},
                {"label": "Repair status", "value": "pending"},
            ],
        },
    }
    checks = checks_by_name(evaluate_ui(case, observed, PDF))
    assert checks["payment_displayed"].passed is True
    assert checks["payment_basis_displayed"].passed is True
    assert checks["conditional_payment_amount"].passed is True
    assert checks["repair_status"].passed is True


def test_scores_are_not_attached_to_a_trace_with_a_different_saved_outcome(monkeypatch):
    import langfuse

    sent = []
    now = datetime.now(UTC)
    root = SimpleNamespace(
        trace_id="trace-1",
        start_time=now,
        end_time=now,
        output={"route": "file_claim", "status": "blocked"},
    )
    api = SimpleNamespace(
        observations=SimpleNamespace(get_many=lambda **kwargs: SimpleNamespace(data=[root])),
        scores=SimpleNamespace(
            get_many=lambda **kwargs: SimpleNamespace(
                data=[SimpleNamespace(id=score["score_id"]) for score in sent]
            )
        ),
    )
    client = SimpleNamespace(
        api=api, create_score=lambda **kwargs: sent.append(kwargs), flush=lambda: None
    )
    monkeypatch.setattr(langfuse, "get_client", lambda: client)
    for key in ("LANGFUSE_TRACING_ENABLED", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.setenv(key, "true")
    checks = [Check("route", True, "file_claim", "file_claim"), Check("semantic", None, True, None)]
    with pytest.raises(ValueError, match="does not match"):
        publish_scores(
            "run", "case", checks, {"workflow": {"route": "file_claim", "phase": "human_review"}}
        )
    assert not sent
    result = publish_scores(
        "run", "case", checks, {"workflow": {"route": "file_claim", "phase": "blocked"}}
    )
    assert result["status"] == "verified" and result["submitted_checks"] == 2
    assert result["unscored_checks"] == 1
    assert any(score["name"] == "ui_eval_unscored_count" and score["value"] == 1 for score in sent)
