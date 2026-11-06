"""Contract and behavioral checks; these do not measure live model accuracy."""

import asyncio
from dataclasses import replace
from decimal import Decimal

import pytest
from langgraph.runtime import Runtime
from pydantic import ValidationError

from app.agents.answer_claim import answer_claim
from app.agents.file_claim import file_claim
from app.agents.lifecycle import begin_request
from app.agents.reviewer import reviewer
from app.agents.router import router
from app.agents.save_claim_status import save_claim_status
from app.agents.support import calculate_estimate
from app.schemas.agents import (
    CoverageDraft,
    IncidentFacts,
    ReviewIssue,
    ReviewVerdict,
    RouteDecision,
    StatusDraft,
)
from tests.fakes import coverage_draft, make_context, make_state, packet_draft


def run(node, state, context):
    return asyncio.run(node(state, Runtime(context=context)))


def drafted_coverage(context):
    context.generator.outputs.append(coverage_draft())
    state = make_state()
    return state | run(answer_claim, state, context)


def test_explicit_route_bypasses_model_and_initialization_is_separate():
    context = make_context()
    state = make_state(explicit_route="file_claim", message="I paid $150; let's file.")
    result = run(router, state, context)
    assert result["route"].route == "file_claim"
    assert not context.generator.calls
    assert "answer" not in result
    assert begin_request(state)["review"] is None


def test_router_preserves_combined_message_for_downstream_agent():
    context = make_context()
    context.generator.outputs.append(RouteDecision(route="file_claim"))
    state = make_state(message="I paid $150; let's file.")
    result = run(router, state, context)
    assert result["route"].route == "file_claim"
    assert context.generator.calls[0]["payload"]["request"]["message"] == state["request"].message
    assert "request" not in result  # Partial state update leaves the original request intact.


def test_ambiguous_route_asks_for_clarification():
    context = make_context()
    context.generator.outputs.append(RouteDecision(route=None, clarification="Which action?"))
    result = run(router, make_state(message="Do it"), context)
    assert result["phase"] == "needs_information"
    assert result["questions"] == ["Which action?"]


def test_answer_stays_private_until_review_and_uses_scoped_retrieval():
    context = make_context()
    state = drafted_coverage(context)
    assert state["answer"] is None
    assert state["phase"] == "review_pending"
    assert state["estimate"].estimated_payment == Decimal("0.00")
    assert context.policies.calls[0]["user_id"] == context.user_id
    assert context.policies.calls[0]["policy_id"] == context.policy_id


@pytest.mark.parametrize("field,value", [("user_id", "other"), ("claim_id", "other")])
def test_wrong_claim_scope_is_rejected(field, value):
    context = make_context()
    context.claims.claim = context.claims.claim.model_copy(update={field: value})
    with pytest.raises(ValueError, match="authorized request"):
        run(answer_claim, make_state(), context)
    assert not context.generator.calls


@pytest.mark.parametrize("field,value", [("policy_id", "other"), ("policy_version", "v0")])
def test_wrong_policy_evidence_is_rejected(field, value):
    context = make_context()
    context.policies.evidence[0] = replace(context.policies.evidence[0], **{field: value})
    with pytest.raises(ValueError, match="another policy or version"):
        run(answer_claim, make_state(), context)


def test_coverage_review_publishes_zero_estimate_and_both_choices():
    context = make_context()
    state = drafted_coverage(context)
    context.reviewer.outputs.append(ReviewVerdict(outcome="pass"))
    result = run(reviewer, state, context)
    assert result["phase"] == "answer_ready"
    assert result["answer"].next_actions == ["save_resolution", "prepare_packet"]
    assert "COVERAGE REVIEW" in context.reviewer.calls[0]["prompt"]
    assert (
        context.reviewer.calls[0]["payload"]["calculated_estimate"]["estimated_payment"] == "0.00"
    )
    assert len(context.policies.calls) == 1  # No additional search without a review evidence gap.


def test_missing_deductible_is_not_assumed_to_be_zero():
    assert calculate_estimate(coverage_draft(deductible=None)) is None


def test_missing_policy_is_uncertainty_not_pass_or_denial():
    context = make_context()
    context.policies.evidence = []
    context.generator.outputs.append(coverage_draft())
    state = make_state()
    state.update(run(answer_claim, state, context))
    result = run(reviewer, state, context)
    assert result["phase"] == "needs_information"
    assert result["answer"] is None
    assert not context.reviewer.calls


def test_fabricated_citation_is_caught_before_llm_review():
    context = make_context()
    context.generator.outputs.append(coverage_draft(citation_ids=["made-up"]))
    state = make_state()
    state.update(run(answer_claim, state, context))
    result = run(reviewer, state, context)
    assert result["phase"] == "revision_required"
    assert result["review"].verdict.issues[0].check == "citation_exists"
    assert not context.reviewer.calls


def test_second_failed_review_blocks_instead_of_looping():
    context = make_context()
    state = drafted_coverage(context)
    verdict = ReviewVerdict(
        outcome="revise",
        issues=[
            ReviewIssue(
                check="unsupported_conclusion",
                detail="The stated cause is missing.",
            )
        ],
    )
    context.reviewer.outputs.extend([verdict, verdict])
    state.update(run(reviewer, state, context))
    assert state["phase"] == "revision_required"
    context.generator.outputs.append(coverage_draft())
    state.update(run(answer_claim, state, context))
    assert state["review"] is None
    assert state["artifact_version"] == 2
    state.update(run(reviewer, state, context))
    assert state["phase"] == "blocked"
    assert state["answer"] is None


def test_review_timeout_never_becomes_a_pass():
    context = make_context()
    state = drafted_coverage(context)
    context.reviewer.outputs.append(TimeoutError("Review unavailable"))
    with pytest.raises(TimeoutError):
        run(reviewer, state, context)
    assert state["answer"] is None
    assert state["review"] is None


def test_status_review_is_separate_and_needs_no_policy_lookup():
    context = make_context()
    context.generator.outputs.append(
        StatusDraft(
            note="User reports the insurer approved the claim.",
            status="user_reported_approved",
        )
    )
    state = make_state("save_claim_status", message="The insurer approved my claim.")
    state.update(run(save_claim_status, state, context))
    context.reviewer.outputs.append(ReviewVerdict(outcome="pass"))
    state.update(run(reviewer, state, context))
    assert state["phase"] == "human_review"
    assert "STATUS REVIEW" in context.reviewer.calls[0]["prompt"]
    assert "COVERAGE REVIEW" not in context.reviewer.calls[0]["prompt"]
    assert not context.policies.calls
    assert context.claims.claim.status == "open"  # Proposal has not been saved.


@pytest.mark.parametrize(
    "node,route",
    [
        (save_claim_status, "save_claim_status"),
        (file_claim, "file_claim"),
    ],
)
def test_action_requires_selected_claim(node, route):
    context = make_context()
    result = run(node, make_state(route, claim_id=None), context)
    assert result["phase"] == "needs_information"
    assert not context.generator.calls


def test_packet_preserves_combined_request_and_allows_zero_payment():
    context = make_context()
    context.generator.outputs.append(packet_draft(context))
    state = make_state("file_claim", message="I paid $150; prepare the packet anyway.")
    state.update(run(file_claim, state, context))
    context.reviewer.outputs.append(ReviewVerdict(outcome="pass"))
    state.update(run(reviewer, state, context))
    assert state["phase"] == "human_review"
    assert state["estimate"].estimated_payment == 0
    assert "PACKET REVIEW" in context.reviewer.calls[0]["prompt"]
    assert context.generator.calls[0]["payload"]["request"]["message"] == state["request"].message


def test_packet_rejects_fabricated_attachment():
    context = make_context()
    context.generator.outputs.append(packet_draft(context, attachment_ids=["invented"]))
    state = make_state("file_claim")
    state.update(run(file_claim, state, context))
    result = run(reviewer, state, context)
    assert result["review"].verdict.issues[0].check == "attachment_exists"


def test_packet_missing_required_date_asks_user():
    context = make_context()
    facts = context.claims.claim.facts.model_copy(update={"occurred_on": None})
    context.generator.outputs.append(packet_draft(context, facts=facts))
    state = make_state("file_claim")
    state.update(run(file_claim, state, context))
    result = run(reviewer, state, context)
    assert result["phase"] == "needs_information"
    assert any("occurred on" in question for question in result["questions"])


@pytest.mark.parametrize("amount", ["-1.00", "NaN", "Infinity", "1.001"])
def test_invalid_money_is_rejected(amount):
    with pytest.raises(ValidationError):
        IncidentFacts(repair_cost=amount)


def test_contradictory_review_result_is_rejected():
    with pytest.raises(ValidationError):
        ReviewVerdict(outcome="pass", questions=["What caused the damage?"])


def test_typed_model_output_cannot_inject_approval_fields():
    with pytest.raises(ValidationError):
        CoverageDraft.model_validate(coverage_draft().model_dump() | {"approved": True})
