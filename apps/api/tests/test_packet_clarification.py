"""Ordinary clarification must reach correction review without inventing confirmation."""

from dataclasses import replace

from app.agents.file_claim import file_claim
from app.agents.lifecycle import begin_request, clarify
from app.agents.reviewer import reviewer
from app.schemas.agents import ReviewVerdict
from tests.fakes import coverage_draft, make_context, make_state, packet_draft
from tests.test_agent_nodes import run


def clarified_state(monkeypatch):
    state = make_state("file_claim", message="Prepare my window claim; the date is unknown.")
    state.update(questions=["When did the window break?"], revision_count=1)
    reply = "The window broke on November 5, 2026; the repair is complete."
    monkeypatch.setattr("app.agents.lifecycle.interrupt", lambda _: {"message": reply})
    state.update(clarify(state))
    return state, reply


def test_clarification_supplements_reports_and_supersedes_old_assessment(monkeypatch):
    ctx = replace(make_context(), prior_coverage={"content": "Incident date unknown", "sources": []})
    state, reply = clarified_state(monkeypatch)
    ctx.generator.outputs.append(packet_draft(ctx))
    run(file_claim, state, ctx)
    payload = ctx.generator.calls[0]["payload"]
    assert payload["requested_edits"] == reply
    assert payload["request"]["message"].endswith("User clarification: " + reply)
    assert "Prepare my window claim" in payload["request"]["message"]
    assert "date is unknown" in payload["earlier_request_and_clarifications"]
    assert payload["confirmed_claim"]["facts"]["cause"] == "Windborne debris"
    assert "previous_reviewed_coverage" not in payload
    assert state["revision_count"] == 0
    assert begin_request(state)["latest_correction"] is None


def test_repeated_answered_question_is_revised_not_asked_again(monkeypatch):
    ctx = make_context()
    state, reply = clarified_state(monkeypatch)
    ctx.generator.outputs.append(packet_draft(ctx, coverage=coverage_draft(
        conclusion="unclear", missing_information=["When did the window break?"]
    )))
    state.update(run(file_claim, state, ctx))
    ctx.reviewer.outputs.append({
        "result": "contradicted",
        "comparison": "The homeowner supplied November 5; asking the date again contradicts that reply.",
    })
    result = run(reviewer, state, ctx)
    assert result["phase"] == "revision_required"
    assert not result["questions"]
    assert result["review"].verdict.issues[0].check == "human_correction"
    assert ctx.reviewer.calls[0]["payload"]["latest_homeowner_correction"] == reply


def test_unrelated_missing_fact_still_requires_clarification(monkeypatch):
    ctx = make_context()
    state, _ = clarified_state(monkeypatch)
    ctx.generator.outputs.append(packet_draft(ctx, coverage=coverage_draft(
        conclusion="unclear", missing_information=["Was the damage to an exterior window?"]
    )))
    state.update(run(file_claim, state, ctx))
    ctx.reviewer.outputs.append({"result": "consistent", "comparison": "Date and repair are retained."})
    result = run(reviewer, state, ctx)
    assert result["phase"] == "needs_information"
    assert result["questions"] == ["Was the damage to an exterior window?"]


def test_uncertain_packet_has_same_conditional_arithmetic_for_reviewer_and_human():
    ctx = make_context()
    state = make_state("file_claim")
    ctx.generator.outputs.append(packet_draft(ctx, coverage=coverage_draft(conclusion="unclear")))
    state.update(run(file_claim, state, ctx))
    ctx.reviewer.outputs.extend([{"unsupported": []}, ReviewVerdict(outcome="pass")])
    result = run(reviewer, state, ctx)
    estimate = ctx.reviewer.calls[-1]["payload"]["calculated_estimate"]
    assert estimate["estimated_payment"] == "0.00"
    assert "If the reported expense is eligible" in estimate["basis"]
    assert result["phase"] == "human_review"
    assert result["estimate"].model_dump(mode="json") == estimate
    assert state["draft"].coverage.conclusion == "unclear"
