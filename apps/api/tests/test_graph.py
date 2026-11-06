import asyncio

from app.agents.checkpoints import memory_checkpointer
from app.agents.graph import build_graph
from app.schemas.agents import ReviewIssue, ReviewVerdict
from tests.fakes import coverage_draft, make_context, make_state


def invoke(context):
    graph = build_graph(memory_checkpointer())
    state = make_state(explicit_route="answer_claim") | {"run_id": "test-run"}
    return asyncio.run(
        graph.ainvoke(state, {"configurable": {"thread_id": "test-run"}}, context=context)
    )


def test_full_graph_refines_once_without_resetting_counter():
    context = make_context()
    context.generator.outputs.extend([coverage_draft(), coverage_draft()])
    rejection = ReviewVerdict(
        outcome="revise",
        issues=[
            ReviewIssue(
                check="support",
                detail="The evidence does not justify this sentence.",
            )
        ],
    )
    context.reviewer.outputs.extend([rejection, rejection])
    result = invoke(context)
    assert result["phase"] == "blocked"
    assert result["answer"] is None
    assert len(context.generator.calls) == len(context.reviewer.calls) == 2
    assert len(context.policies.calls) == 1


def test_full_graph_corrects_bad_citation_before_publishing():
    context = make_context()
    context.generator.outputs.extend([coverage_draft(citation_ids=["invented"]), coverage_draft()])
    context.reviewer.outputs.append(ReviewVerdict(outcome="pass"))
    result = invoke(context)
    assert result["phase"] == "answer_ready"
    assert result["artifact_version"] == 2
    assert result["answer"].coverage.citation_ids == ["wind-clause"]
