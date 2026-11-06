"""Use a one-node graph to verify actual LangGraph interrupt/resume behavior."""

import asyncio

import pytest
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command

from app.agents.checkpoints import memory_checkpointer
from app.agents.context import AgentContext
from app.agents.human_review import human_review
from app.agents.state import AgentState
from app.schemas.agents import ReviewResult, ReviewVerdict, StatusDraft
from tests.fakes import make_context, make_state


def awaiting_review(context):
    return make_state("save_claim_status") | {
        "claim": context.claims.claim,
        "draft": StatusDraft(note="The repair is complete."),
        "artifact_version": 3,
        "phase": "human_review",
        "review": ReviewResult(
            route="save_claim_status",
            artifact_version=3,
            verdict=ReviewVerdict(outcome="pass"),
        ),
    }


def single_node_graph():
    builder = StateGraph(AgentState, context_schema=AgentContext)
    builder.add_node("human_review", human_review)
    builder.add_edge(START, "human_review")
    builder.add_edge("human_review", END)
    return builder.compile(checkpointer=memory_checkpointer())


@pytest.mark.parametrize("action,phase", [("approve", "approved"), ("reject", "rejected")])
def test_human_pause_and_resume(action, phase):
    context = make_context()
    graph = single_node_graph()
    config = {"configurable": {"thread_id": "review-test"}}

    async def scenario():
        result = await graph.ainvoke(awaiting_review(context), config, context=context)
        assert result["__interrupt__"][0].value["artifact_version"] == 3
        assert "human_decision" not in result
        return await graph.ainvoke(
            Command(resume={"artifact_version": 3, "action": action}),
            config,
            context=context,
        )

    result = asyncio.run(scenario())
    assert result["phase"] == phase
    assert context.claims.claim.status == "open"
    assert not context.generator.calls and not context.reviewer.calls


def test_human_edit_invalidates_review_and_requests_regeneration():
    context = make_context()
    graph = single_node_graph()
    config = {"configurable": {"thread_id": "edit-test"}}

    async def scenario():
        await graph.ainvoke(awaiting_review(context), config, context=context)
        return await graph.ainvoke(
            Command(
                resume={
                    "artifact_version": 3,
                    "action": "edit",
                    "feedback": "The cost was $175.",
                }
            ),
            config,
            context=context,
        )

    result = asyncio.run(scenario())
    assert result["phase"] == "revision_required"
    assert result["review"] is None
    assert result["human_decision"].feedback == "The cost was $175."


@pytest.mark.parametrize("stale_record", [False, True])
def test_stale_human_decision_is_rejected(stale_record):
    context = make_context()
    graph = single_node_graph()
    config = {"configurable": {"thread_id": "stale-test"}}

    async def scenario():
        await graph.ainvoke(awaiting_review(context), config, context=context)
        if stale_record:
            context.claims.claim = context.claims.claim.model_copy(update={"version": 2})
        await graph.ainvoke(
            Command(
                resume={
                    "artifact_version": 3 if stale_record else 2,
                    "action": "approve",
                }
            ),
            config,
            context=context,
        )

    with pytest.raises(ValueError, match="changed while awaiting|older artifact"):
        asyncio.run(scenario())


def test_human_review_cannot_bypass_failed_review():
    context = make_context()
    state = awaiting_review(context)
    state["review"] = None
    with pytest.raises(ValueError, match="passed action review"):
        asyncio.run(human_review(state, Runtime(context=context)))
