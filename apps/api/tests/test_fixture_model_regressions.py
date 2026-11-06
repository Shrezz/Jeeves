"""Regression checks for the deterministic synthetic demo model."""

import asyncio

import pytest

from app.schemas.agents import CoverageDraft, RouteDecision
from app.services.fixtures import FixtureModel, FixtureStore


def generate(message, output_type, *, cause="Windborne debris"):
    store = FixtureStore.seeded()
    claim = store.claims["demo-window"]
    claim = claim.model_copy(update={"facts": claim.facts.model_copy(update={"cause": cause})})
    return asyncio.run(
        FixtureModel().generate(
            prompt="synthetic only",
            payload={
                "request": {"message": message},
                "confirmed_claim": claim.model_dump(mode="json"),
                "evidence": [{"chunk_id": "demo-wind"}],
            },
            output_type=output_type,
        )
    )


def test_completed_repair_is_status_update():
    assert generate("The window repair is complete.", RouteDecision).route == "save_claim_status"


@pytest.mark.parametrize("cause", ["Wear and tear", "Earthquake"])
def test_window_word_does_not_change_incident_cause_to_wind(cause):
    draft = generate("Is my window covered?", CoverageDraft, cause=cause)
    assert draft.conclusion == ("likely_not_covered" if cause == "Wear and tear" else "unclear")


def test_unsupported_glass_treatment_is_not_assessed_as_wind_damage():
    draft = generate("Does my policy cover this unusual glass treatment?", CoverageDraft)
    assert draft.conclusion == "unclear"
    assert draft.missing_information
    assert draft.covered_amount is None and draft.deductible is None


@pytest.mark.parametrize(
    "question", ["Is stolen jewelry covered?", "Does my policy cover flood damage?"]
)
def test_other_unsupported_topics_do_not_inherit_window_coverage(question):
    draft = generate(question, CoverageDraft)
    assert draft.conclusion == "unclear"
    assert draft.missing_information


def test_known_but_unaddressed_cause_asks_for_policy_evidence():
    draft = generate("Is my window covered?", CoverageDraft, cause="Earthquake")
    assert draft.conclusion == "unclear"
    assert "policy evidence" in draft.missing_information[0]


def test_explicit_worn_out_cause_takes_precedence_over_old_claim_facts():
    draft = generate("The window was worn out. Is it covered?", CoverageDraft)
    assert draft.conclusion == "likely_not_covered"
    assert "wear" in draft.explanation.lower()
