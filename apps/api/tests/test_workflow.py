"""Contract tests for safe, deterministic workflow primitives."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.agents.workflow import estimate_payment, route_message
from app.main import app


@pytest.mark.parametrize(("message", "expected"), [
    ("Is my broken window covered?", "answer_claim"),
    ("Does my policy cover worn-out glass?", "answer_claim"),
    ("I paid $150. Let's file.", "file_claim"),
    ("Prepare a claim for the broken window", "file_claim"),
    ("The repair is complete", "save_claim_status"),
    ("The insurer asked for photos", "save_claim_status"),
])
def test_routes(message: str, expected: str) -> None:
    selected = "claim-demo" if expected == "save_claim_status" else None
    decision = route_message(message, selected_claim_id=selected)
    assert decision.intent == expected
    assert not decision.needs_clarification


def test_status_update_requires_case_selection() -> None:
    decision = route_message("The repair is complete")
    assert decision.intent == "save_claim_status"
    assert decision.needs_clarification


def test_mixed_request_requires_clarification() -> None:
    decision = route_message("Update status and file my claim")
    assert decision.needs_clarification
    assert decision.intent is None


def test_unknown_intent_is_not_guessed() -> None:
    assert route_message("Hello").needs_clarification


def test_estimates() -> None:
    assert estimate_payment("150", "1000") == Decimal("0.00")
    assert estimate_payment("1400", "1000") == Decimal("400.00")
    assert estimate_payment("2500", "1000") == Decimal("1500.00")


@pytest.mark.parametrize(("loss", "deductible"), [
    ("-1", "1000"), ("NaN", "1000"), ("150", "-10"), ("inf", "1000")
])
def test_invalid_estimates(loss: str, deductible: str) -> None:
    with pytest.raises(ValueError):
        estimate_payment(loss, deductible)


def test_read_only_http_contract() -> None:
    client = TestClient(app)
    assert client.post("/workflow/route", json={
        "message": "The repair is complete",
        "selected_claim_id": "claim-demo",
    }).json()["intent"] == "save_claim_status"
    response = client.post("/workflow/estimate", json={
        "eligible_loss": 150, "deductible": 1000
    })
    assert response.status_code == 200
    assert response.json()["estimated_payment"] == "0.00"
