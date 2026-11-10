"""Evaluate stored fictional UI outputs without a model or a live Langfuse account."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "evals"))

from evaluators import Check
from ui_workflow_eval import evaluate_ui, load_case, source_integrity

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


def test_fixture_declarations_banner_is_not_a_false_citation_failure():
    from ui_workflow_eval import source_integrity

    quote = "01 / DECLARATIONS\nHomeowners policy\nPolicy number CCV-HO3-CA-100731"
    source = {"page": 1, "chunkId": "policy:0", "excerpt": quote}
    assert source_integrity([source], "policy", PDF)
    assert not source_integrity(
        [{**source, "excerpt": quote.replace("100731", "999999")}], "policy", PDF
    )
    # Never permit omitting a material word from a clause.
    assert not source_integrity(
        [{"page": 2, "chunkId": "policy:1", "excerpt": "Gradual wear and damage are covered"}],
        "policy",
        PDF,
    )


@pytest.mark.parametrize("delivery", ["verified", "submitted_not_yet_visible"])
@pytest.mark.parametrize("strict", [False, True])
def test_cli_export_is_not_successful_without_verified_delivery(
    monkeypatch, delivery, strict, capsys
):
    import ui_workflow_eval as module

    monkeypatch.setenv("UI_EVAL_DATABASE_URL", "synthetic://not-connected")
    monkeypatch.setattr(module, "load_case", lambda *args: {"id": "synthetic", "message_terms": []})
    monkeypatch.setattr(module, "load_observation", lambda *args: ({"message": ""}, b""))
    monkeypatch.setattr(module, "evaluate_ui", lambda *args: [Check("phase", True, "x", "x")])
    monkeypatch.setattr(module, "publish_scores", lambda *args, **kwargs: {"status": delivery})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ui_workflow_eval",
            "--run-id",
            "00000000-0000-0000-0000-000000000001",
            "--case-id",
            "synthetic",
            "--langfuse",
            *(["--strict"] if strict else []),
        ],
    )
    assert module.main() == (0 if delivery == "verified" else 1)
    capsys.readouterr()
