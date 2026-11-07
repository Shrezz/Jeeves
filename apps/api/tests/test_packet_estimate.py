from dataclasses import replace
from decimal import Decimal

from app.agents.packet_estimate import explicit_flat_terms
from app.agents.support import calculate_estimate
from tests.fakes import make_context, packet_draft

FORMULA = "Estimated payment for an eligible loss max(0, min(eligible expense, $2,000) - $750)"


def test_conditional_math_uses_the_cited_formula_without_deciding_the_peril():
    ctx = make_context()
    cite = replace(ctx.policies.evidence[0], excerpt=FORMULA, chunk_id="C9")
    terms = explicit_flat_terms([cite])
    draft = packet_draft(ctx)
    draft = draft.model_copy(
        update={
            "facts": draft.facts.model_copy(update={"repair_cost": Decimal(2300)}),
            "coverage": draft.coverage.model_copy(
                update={"conclusion": "unclear", "citation_ids": ["C4"]}
            ),
        }
    )
    proposal = terms.apply(draft)
    assert proposal.coverage.conclusion == "unclear" and proposal.facts == draft.facts
    assert proposal.coverage.citation_ids == ["C4", "C9"]
    assert calculate_estimate(proposal.coverage, if_eligible=True).estimated_payment == 1250


def test_conflicting_terms_examples_and_missing_cost_do_not_create_an_estimate():
    ctx = make_context()
    cite = replace(ctx.policies.evidence[0], excerpt=FORMULA)
    assert explicit_flat_terms([cite, replace(cite, excerpt=FORMULA.replace("750", "950"))]) is None
    assert (
        explicit_flat_terms([replace(cite, excerpt="Illustrative calculations: " + FORMULA)])
        is None
    )
    draft = packet_draft(ctx)
    draft = draft.model_copy(update={"facts": draft.facts.model_copy(update={"repair_cost": None})})
    assert explicit_flat_terms([cite]).apply(draft) is draft
