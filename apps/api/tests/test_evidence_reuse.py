import asyncio
from dataclasses import replace

from langgraph.runtime import Runtime

from app.agents.answer_claim import answer_claim
from app.agents.file_claim import file_claim
from app.agents.reviewer import reviewer
from app.schemas.agents import EvidencePlan, ReviewVerdict
from tests.fakes import coverage_draft, make_context, make_state, packet_draft


def run(node, state, context):
    return asyncio.run(node(state, Runtime(context=context)))


def reviewed_coverage(context):
    state = make_state()
    context.generator.outputs.append(coverage_draft())
    state.update(run(answer_claim, state, context))
    context.reviewer.outputs.append(ReviewVerdict(outcome="pass"))
    state.update(run(reviewer, state, context))
    return state


def test_reviewed_coverage_can_be_reused_for_filing():
    context = make_context()
    reviewed_coverage(context)
    context.generator.outputs.extend([EvidencePlan(reuse=True), packet_draft(context)])
    run(file_claim, make_state("file_claim", message="I paid $150. File the claim."), context)
    assert len(context.policies.calls) == 1


def test_new_cause_refreshes():
    context = make_context()
    reviewed_coverage(context)
    context.claims.claim = context.claims.claim.model_copy(
        update={
            "facts": context.claims.claim.facts.model_copy(update={"cause": "Flood"}),
        }
    )
    context.generator.outputs.append(packet_draft(context))
    run(file_claim, make_state("file_claim", message="Prepare the claim"), context)
    assert len(context.policies.calls) == 2


def test_repair_amount_change_reuses_passages_with_a_new_assessment():
    context = make_context()
    reviewed_coverage(context)
    from decimal import Decimal

    context.claims.claim = context.claims.claim.model_copy(
        update={
            "facts": context.claims.claim.facts.model_copy(update={"repair_cost": Decimal(175)}),
        }
    )
    context.generator.outputs.extend([EvidencePlan(reuse=True), packet_draft(context)])
    result = run(
        file_claim, make_state("file_claim", message="Prepare the repaired window claim"), context
    )
    assert len(context.policies.calls) == 1
    assert result["review"] is None
    assert result["phase"] == "review_pending"


def test_new_topic_in_message_can_force_refresh_even_before_db_changes():
    context = make_context()
    reviewed_coverage(context)
    context.generator.outputs.extend(
        [EvidencePlan(reuse=False, query="Flood damage exclusions"), packet_draft(context)]
    )
    run(
        file_claim,
        make_state("file_claim", message="Actually it was flood damage. Prepare the claim."),
        context,
    )
    assert len(context.policies.calls) == 2
    assert context.policies.calls[-1]["question"] == "Flood damage exclusions"


def test_policy_version_change_cannot_reuse_old_evidence():
    context = make_context()
    reviewed_coverage(context)
    changed = replace(context, policy_version="v2")
    changed.claims.claim = context.claims.claim.model_copy(update={"policy_version": "v2"})
    changed.policies.evidence[0] = replace(changed.policies.evidence[0], policy_version="v2")
    changed.generator.outputs.append(coverage_draft())
    run(answer_claim, make_state(), changed)
    assert len(context.policies.calls) == 2


def test_reviewer_fetches_only_when_it_identifies_an_evidence_gap():
    context = make_context()
    context.generator.outputs.append(coverage_draft())
    state = make_state()
    state.update(run(answer_claim, state, context))
    context.reviewer.outputs.extend(
        [
            ReviewVerdict(
                outcome="needs_information",
                questions=["What exclusions apply?"],
                evidence_query="Window wind exclusions",
            ),
            ReviewVerdict(outcome="pass"),
        ]
    )
    result = run(reviewer, state, context)
    assert result["phase"] == "answer_ready"
    assert len(context.policies.calls) == 2
    assert context.policies.calls[-1]["question"] == "Window wind exclusions"


def test_reviewer_cannot_start_an_unbounded_retrieval_loop():
    context = make_context()
    context.generator.outputs.append(coverage_draft())
    state = make_state()
    state.update(run(answer_claim, state, context))
    gap = ReviewVerdict(
        outcome="needs_information",
        questions=["Missing policy clause?"],
        evidence_query="More policy terms",
    )
    context.reviewer.outputs.extend([gap, gap])
    assert run(reviewer, state, context)["phase"] == "needs_information"
    assert len(context.policies.calls) == 2
