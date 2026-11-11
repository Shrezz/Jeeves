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


def test_unconfirmed_peril_only_has_an_explicitly_conditional_packet_estimate():
    uncertain = coverage_draft(conclusion="unclear", missing_information=["Peril unconfirmed"])
    assert calculate_estimate(uncertain) is None
    estimate = calculate_estimate(uncertain, if_eligible=True)
    assert (
        estimate.estimated_payment == 0 and "If the reported expense is eligible" in estimate.basis
    )
    for change in (
        {"deductible": None},
        {"covered_amount": None},
        {"citation_ids": []},
        {"conclusion": "likely_not_covered"},
    ):
        assert calculate_estimate(uncertain.model_copy(update=change), if_eligible=True) is None


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
            status="insurer_decision_received",
            insurer_outcome="approved",
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
    assert context.claims.claim.status == "draft"  # Proposal has not been saved.


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
    context.reviewer.outputs.extend([{"unsupported": []}, ReviewVerdict(outcome="pass")])
    state.update(run(reviewer, state, context))
    assert state["phase"] == "human_review"
    assert state["estimate"].estimated_payment == 0
    assert "PACKET REVIEW" in context.reviewer.calls[1]["prompt"]
    assert context.generator.calls[0]["payload"]["request"]["message"] == state["request"].message


def test_pending_clarification_survives_generator_and_keeps_other_uncertainties(monkeypatch):
    from app.agents.lifecycle import clarify

    context = make_context()
    state = make_state("file_claim")
    state["questions"] = ["Is the repair pending?"]
    monkeypatch.setattr(
        "app.agents.lifecycle.interrupt",
        lambda _: {"message": "The window repair is pending; no boarding was performed."},
    )
    state.update(clarify(state))
    context.generator.outputs.append(
        packet_draft(
            context,
            facts=context.claims.claim.facts.model_copy(update={"repair_status": "unknown"}),
            missing_information=[
                "The repair status is unknown; confirmation of completion or pending status is needed.",
                "Was the window already broken before the storm?",
            ],
        )
    )
    result = run(file_claim, state, context)
    assert result["draft"].facts.repair_status == "pending"
    assert result["draft"].missing_information == [
        "Was the window already broken before the storm?"
    ]
    assert context.generator.calls[0]["payload"]["clarified_repair_status"] == "pending"


def test_pending_repair_cannot_be_passed_with_completed_narrative():
    context = make_context()
    facts = context.claims.claim.facts.model_copy(update={"repair_status": "pending"})
    context.generator.outputs.append(
        packet_draft(context, facts=facts, narrative="The repair was completed yesterday.")
    )
    state = make_state("file_claim")
    state.update(run(file_claim, state, context))
    state.update(run(reviewer, state, context))
    assert state["phase"] == "revision_required"
    assert any(
        issue.check == "repair_status_consistency" for issue in state["review"].verdict.issues
    )
    assert not context.reviewer.calls


def test_packet_cannot_invent_previous_window_condition():
    context = make_context()
    context.generator.outputs.append(
        packet_draft(
            context, narrative="A window broke and the window was intact before the storm."
        )
    )
    state = make_state("file_claim")
    state.update(run(file_claim, state, context))
    state.update(run(reviewer, state, context))
    assert state["phase"] == "revision_required"
    assert any(
        issue.check == "unsupported_prior_condition" for issue in state["review"].verdict.issues
    )
    assert not context.reviewer.calls


@pytest.mark.parametrize(
    "answer", ["The repair is not pending.", "The repair is pending but completed."]
)
def test_ambiguous_or_negated_pending_is_not_recorded(monkeypatch, answer):
    from app.agents.lifecycle import clarify

    state = make_state("file_claim")
    state["questions"] = ["Is the repair pending?"]
    monkeypatch.setattr("app.agents.lifecycle.interrupt", lambda _: {"message": answer})
    assert clarify(state)["clarified_repair_status"] is None


def test_later_explicit_repair_correction_replaces_pending(monkeypatch):
    from app.agents.human_review import human_review
    from app.schemas.agents import ReviewResult

    context = make_context()
    state = make_state("file_claim")
    state.update(
        claim=context.claims.claim,
        draft=packet_draft(context),
        artifact_version=1,
        estimate=None,
        clarified_repair_status="pending",
        review=ReviewResult(
            route="file_claim", artifact_version=1, verdict=ReviewVerdict(outcome="pass")
        ),
    )
    monkeypatch.setattr(
        "app.agents.human_review.interrupt",
        lambda _: {
            "artifact_version": 1,
            "action": "edit",
            "feedback": "The repair was completed.",
        },
    )
    update = run(human_review, state, context)
    assert update["clarified_repair_status"] == "completed"
    state.update(update)
    context.generator.outputs.append(packet_draft(context))
    revised = run(file_claim, state, context)
    assert revised["draft"].facts.repair_status == "completed"


def test_optional_invoice_is_reviewed_without_requiring_an_upload():
    context = make_context()
    context.generator.outputs.append(
        packet_draft(
            context,
            coverage=coverage_draft(missing_information=["Invoice has not been uploaded."]),
            attachment_ids=[],
            missing_information=["Attach the invoice if available."],
        )
    )
    state = make_state("file_claim")
    state.update(run(file_claim, state, context))
    context.reviewer.outputs.extend([{"unsupported": []}, ReviewVerdict(outcome="pass")])
    state.update(run(reviewer, state, context))
    assert state["phase"] == "human_review"
    assert state["estimate"].estimated_payment == 0
    assert "If the reported expense is eligible" in state["estimate"].basis
    assert context.reviewer.calls[1]["payload"]["calculated_estimate"] == state[
        "estimate"
    ].model_dump(mode="json")


def test_unresolved_coverage_cannot_be_cleared_into_an_estimate():
    context = make_context()
    context.generator.outputs.append(
        packet_draft(
            context,
            coverage=coverage_draft(
                missing_information=["Was the window already broken before the storm?"]
            ),
        )
    )
    state = make_state("file_claim")
    state.update(run(file_claim, state, context))
    state.update(run(reviewer, state, context))
    assert state["phase"] == "needs_information"
    assert state["estimate"] is None
    assert any("already broken" in question for question in state["questions"])
    assert not context.reviewer.calls


def test_packet_cannot_treat_a_zero_payment_as_zero_eligible_expense():
    context = make_context()
    context.generator.outputs.append(
        packet_draft(context, coverage=coverage_draft(covered_amount="0"))
    )
    state = make_state("file_claim")
    state.update(run(file_claim, state, context))
    state.update(run(reviewer, state, context))
    assert state["phase"] == "revision_required"
    assert any(issue.check == "gross_expense" for issue in state["review"].verdict.issues)


@pytest.mark.parametrize("covered_amount", ["300.00", "400.00"])
def test_packet_flags_unverified_reduction_before_human_review(covered_amount):
    context = make_context()
    facts = context.claims.claim.facts.model_copy(update={"repair_cost": Decimal("1400.00")})
    context.generator.outputs.append(
        packet_draft(context, facts=facts, coverage=coverage_draft(covered_amount=covered_amount))
    )
    state = make_state("file_claim")
    state.update(run(file_claim, state, context))
    state.update(run(reviewer, state, context))
    assert state["phase"] == "revision_required"
    assert any(issue.check == "gross_expense" for issue in state["review"].verdict.issues)


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


@pytest.mark.parametrize("deductible,payment", [("1000", "0.00"), ("100", "50.00"), (None, None)])
@pytest.mark.parametrize("extra_search", [False, True])
def test_packet_review_includes_server_payment_in_artifact(deductible, payment, extra_search):
    context = make_context()
    context.generator.outputs.append(
        packet_draft(context, coverage=coverage_draft(deductible=deductible))
    )
    state = make_state("file_claim")
    state.update(run(file_claim, state, context))
    before = state["draft"].model_dump(mode="json")
    context.reviewer.outputs.append({"unsupported": []})
    if extra_search:
        context.reviewer.outputs.append(
            ReviewVerdict(outcome="needs_information", questions=["Policy wording?"],
                          evidence_query="deductible")
        )
    context.reviewer.outputs.append(ReviewVerdict(outcome="pass"))
    result = run(reviewer, state, context)
    assert result["phase"] == "human_review"
    for call in context.reviewer.calls[1:]:
        payload = call["payload"]
        calculation = payload["draft"]["calculated_estimate"]
        assert calculation == payload["calculated_estimate"]
        if payment is None:
            assert calculation is None
        else:
            assert calculation["estimated_payment"] == payment
    assert state["draft"].model_dump(mode="json") == before
