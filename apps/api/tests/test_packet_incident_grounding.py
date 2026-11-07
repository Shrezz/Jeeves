from dataclasses import replace

import pytest

from app.agents.reviewer import reviewer
from app.schemas.agents import IncidentFacts, ReviewVerdict
from tests.fakes import coverage_draft, make_context, make_state, packet_draft
from tests.test_agent_nodes import run

REPORT = "Wind blew a tree branch through my window"
OLD_CAUSE = "Impact by windblown debris during a windstorm (suddenly falling tree branch)"


def window_packet(report=REPORT, *, cause=None, narrative=None):
    ctx = replace(make_context(), prior_coverage={"answer": "A windstorm occurred."})
    claim = ctx.claims.claim.model_copy(
        update={
            "facts": IncidentFacts(occurred_on="2026-11-05", repair_cost=150),
            "notes": [f"{report}. I paid $150 to repair it."],
        }
    )
    evidence = [
        replace(ctx.policies.evidence[0], chunk_id="C1", section="Perils", excerpt=OLD_CAUSE)
    ]
    draft = packet_draft(
        ctx,
        facts=claim.facts.model_copy(update={"cause": cause or report, "description": report}),
        narrative=narrative or report,
        coverage=coverage_draft(
            citation_ids=["C1"], explanation="If a windstorm occurred, the cited peril may apply."
        ),
    )
    state = make_state("file_claim", message="Prepare the packet.")
    state.update(draft=draft, claim=claim, evidence=evidence, artifact_version=2)
    return ctx, state


def test_policy_and_prior_answer_cannot_supply_the_incident_cause():
    ctx, state = window_packet(cause=OLD_CAUSE)
    for count, phase in [(0, "revision_required"), (1, "blocked")]:
        result = run(reviewer, {**state, "revision_count": count}, ctx)
        assert result["phase"] == phase
        issue = result["review"].verdict.issues[0]
        assert (issue.check, issue.field) == ("incident_grounding", "facts.cause")
    assert not ctx.reviewer.calls


@pytest.mark.parametrize(
    ("report", "cause", "narrative", "field"),
    [
        (REPORT, REPORT, "A severe storm caused a branch to fall suddenly.", "narrative"),
        (
            "I cannot confirm a windstorm",
            "windstorm",
            "A windstorm broke the window.",
            "facts.cause",
        ),
    ],
)
def test_semantic_fact_audit_can_veto_an_otherwise_valid_packet(report, cause, narrative, field):
    ctx, state = window_packet(report, cause=cause, narrative=narrative)
    ctx.reviewer.outputs.append(
        {"unsupported": [{"field": field, "detail": "Weather severity is unconfirmed."}]}
    )
    result = run(reviewer, state, ctx)
    assert result["phase"] == "revision_required"
    payload = ctx.reviewer.calls[0]["payload"]
    assert any(text.startswith(report) for text in payload["homeowner_reports"])
    assert set(payload) == {
        "homeowner_reports",
        "confirmed_incident",
        "proposed_facts",
        "proposed_narrative",
    }
    assert len(ctx.reviewer.calls) == 1


@pytest.mark.parametrize("report", [REPORT, "I saw the windstorm blow a branch through my window"])
def test_confirmed_storm_or_conditional_policy_language_can_pass(report):
    ctx, state = window_packet(report)
    ctx.reviewer.outputs.extend([{"unsupported": []}, ReviewVerdict(outcome="pass")])
    assert run(reviewer, state, ctx)["phase"] == "human_review"
    assert ctx.reviewer.calls[1]["payload"]["evidence"]


def test_human_edit_is_checked_even_after_the_approval_decision_was_cleared():
    ctx, state = window_packet()
    correction = "It was windblown debris during a windstorm."
    state.update(latest_correction=correction, human_decision=None)
    ctx.reviewer.outputs.extend(
        [
            {"unsupported": []},
            {
                "result": "contradicted",
                "comparison": "Coverage still treats the confirmed windstorm as hypothetical.",
            },
        ]
    )
    result = run(reviewer, state, ctx)
    assert result["phase"] == "revision_required"
    assert result["review"].verdict.issues[0].check == "human_correction"
    audit = ctx.reviewer.calls[-1]["payload"]
    assert audit["latest_homeowner_correction"] == correction
    assert audit["revised_packet"]["coverage"]["explanation"] == state["draft"].coverage.explanation
    assert "previous_reviewed_coverage" not in audit


def test_named_cause_requires_an_affirmed_sentence_and_cited_list():
    from app.agents.named_peril import apply_named_cause

    ctx, state = window_packet()
    item = replace(
        ctx.policies.evidence[0],
        chunk_id="C4",
        excerpt="2.2 Covered causes\nCovered causes are a suddenly falling tree branch, impact by windblown debris during a windstorm, and accidental sports-ball impact.",
    )
    draft = state["draft"]
    correction = "It was windblown debris during a windstorm."
    revised = apply_named_cause(draft, correction, [item])
    assert revised.facts.cause == "windblown debris during a windstorm"
    assert revised.coverage.citation_ids[0] == "C4"
    assert apply_named_cause(draft, "Was it windblown debris during a windstorm?", [item]) is draft
    assert (
        apply_named_cause(draft, "It was not windblown debris during a windstorm.", [item]) is draft
    )
    assert apply_named_cause(draft, correction, []) is draft
