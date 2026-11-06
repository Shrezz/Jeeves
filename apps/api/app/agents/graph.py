"""Explicit connections for the three routes, bounded review, and human decisions."""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.observability.agent_nodes import instrument_node

from .answer_claim import answer_claim
from .context import AgentContext
from .file_claim import file_claim
from .human_review import human_review
from .lifecycle import begin_request, clarify, commit_action
from .reviewer import reviewer
from .router import router
from .save_claim_status import save_claim_status
from .state import AgentState


def selected_agent(state: AgentState) -> str:
    return state["route"].route or "clarify"


def after_draft(state: AgentState) -> str:
    return "clarify" if state["phase"] == "needs_information" else "reviewer"


def after_review(state: AgentState) -> str:
    if state["phase"] == "revision_required":
        return selected_agent(state)
    return {"needs_information": "clarify", "human_review": "human_review"}.get(state["phase"], END)


def after_human(state: AgentState) -> str:
    if state["phase"] == "revision_required":
        return selected_agent(state)
    return "commit_action" if state["phase"] == "approved" else END


def after_clarification(state: AgentState) -> str:
    return state["route"].route or "router"


def build_graph(checkpointer: BaseCheckpointSaver):
    """Inject a checkpointer; the demo uses memory, deployment supplies durable storage."""
    graph = StateGraph(AgentState, context_schema=AgentContext)
    for name, node in {
        "begin_request": begin_request,
        "router": router,
        "answer_claim": answer_claim,
        "save_claim_status": save_claim_status,
        "file_claim": file_claim,
        "reviewer": reviewer,
        "human_review": human_review,
        "clarify": clarify,
        "commit_action": commit_action,
    }.items():
        graph.add_node(name, instrument_node(name, node))
    graph.add_edge(START, "begin_request")
    graph.add_edge("begin_request", "router")
    routes = ["answer_claim", "save_claim_status", "file_claim"]
    graph.add_conditional_edges("router", selected_agent, routes + ["clarify"])
    for name in routes:
        graph.add_conditional_edges(name, after_draft, ["reviewer", "clarify"])
    graph.add_conditional_edges("reviewer", after_review, routes + ["clarify", "human_review", END])
    graph.add_conditional_edges("human_review", after_human, routes + ["commit_action", END])
    graph.add_conditional_edges("clarify", after_clarification, routes + ["router"])
    graph.add_edge("commit_action", END)
    return graph.compile(checkpointer=checkpointer)
