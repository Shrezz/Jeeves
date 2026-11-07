"""Shared identity and lifecycle boundaries must preserve user meaning."""

import asyncio
import json
from pathlib import Path
from typing import get_args

import pytest
from pydantic import ValidationError

from app.schemas.agents import ClaimSnapshot, IncidentFacts, StatusDraft
from app.schemas.domain import CLAIM_STATUS_LABELS, ClaimStatus, RunStatus
from app.services.fixtures import FixtureStore
from app.services.identity import clerk_user_id, owned_record_user_id
from app.services.status_mapping import map_legacy_status


def test_verified_clerk_subject_is_preserved_across_boundaries():
    subject = "user_2Example"
    assert owned_record_user_id({"owner_id": subject}, subject) == subject
    with pytest.raises(PermissionError):
        owned_record_user_id({"owner_id": "user_Other"}, subject)
    with pytest.raises(PermissionError):
        owned_record_user_id({"email": "same@example.test"}, subject)


@pytest.mark.parametrize("subject", ["", "demo-user", "a@example.test", "user_", " user_123"])
def test_identity_mapper_rejects_non_clerk_identifiers(subject):
    with pytest.raises(ValueError):
        clerk_user_id(subject)


def test_repair_update_does_not_change_filing_progress():
    mapped = map_legacy_status("repaired", current_status="filed_by_user")
    assert mapped.status is None and mapped.repair_status == "completed"
    assert map_legacy_status("open", current_status="prepared").status == "prepared"


@pytest.mark.parametrize(
    "value", ["resolved", "filed_demo", "needs_info", "awaiting_review", "action_failed"]
)
def test_ambiguous_or_execution_states_are_not_silently_lifecycle_states(value):
    with pytest.raises(ValueError, match="reconciliation"):
        map_legacy_status(value)


def test_reported_decisions_and_explicit_no_filing_resolution():
    result = map_legacy_status("user_reported_denied")
    assert result.status == "insurer_decision_received"
    assert result.insurer_outcome == "denied"
    assert (
        map_legacy_status("resolved", without_filing_confirmed=True).status
        == "resolved_without_filing"
    )


@pytest.mark.parametrize(
    "status", ["prepared", "preparation_requested", "awaiting_review", "repaired"]
)
def test_status_agent_cannot_manufacture_packets_or_mix_status_domains(status):
    with pytest.raises(ValidationError):
        StatusDraft(note="A user update", status=status)


def test_insurer_outcome_requires_a_reported_decision():
    with pytest.raises(ValidationError):
        StatusDraft(note="The user paid for repairs", insurer_outcome="approved")


def test_committed_user_reported_outcome_preserves_repair_facts():
    store = FixtureStore.seeded()
    claim = store.claims["demo-window"]
    proposal = StatusDraft(
        note="User reports the insurer denied this claim.",
        status="insurer_decision_received",
        insurer_outcome="denied",
        facts=IncidentFacts(repair_status="completed"),
    )
    asyncio.run(
        store.commit(
            user_id="demo-user", claim=claim, proposal=proposal, evidence=[], request_key="reported"
        )
    )
    saved = store.claims[claim.claim_id]
    assert saved.status == "insurer_decision_received"
    assert saved.insurer_outcome == "denied" and saved.insurer_outcome_source == "user_reported"
    assert saved.facts.repair_status == "completed"
    assert saved.notes == [proposal.note]


def test_shared_values_match_python_and_are_distinct_from_run_status():
    root = Path(__file__).resolve().parents[3]
    contract = json.loads((root / "packages/contracts/domain.json").read_text())
    assert list(get_args(ClaimStatus)) == list(contract["claim_status"])
    assert CLAIM_STATUS_LABELS == contract["claim_status"]
    assert list(get_args(RunStatus)) == contract["run_status"]
    assert "awaiting_review" not in get_args(ClaimStatus)
    assert ClaimSnapshot.model_fields["status"].default == "draft"
