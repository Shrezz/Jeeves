"""Request initialization, clarification, and approved actions are deterministic workflow steps."""

from langgraph.runtime import Runtime
from langgraph.types import interrupt

from app.schemas.agents import Clarification, PacketDraft, StatusDraft

from .context import AgentContext
from .repair_status import reconcile_repair_status
from .state import AgentState
from .support import load_claim


def begin_request(state: AgentState) -> AgentState:
    return {
        "claim": None,
        "draft": None,
        "evidence": [],
        "estimate": None,
        "review": None,
        "answer": None,
        "human_decision": None,
        "revision_count": 0,
        "questions": [],
        "action_result": None,
        "clarified_repair_status": None,
        "latest_correction": None,
        "artifact_version": 0,
    }


def clarify(state: AgentState) -> AgentState:
    reply = Clarification.model_validate(
        interrupt(
            {
                "kind": "clarification",
                "questions": state["questions"],
            }
        )
    )
    request = state["request"].model_copy(
        update={
            "message": state["request"].message + "\nUser clarification: " + reply.message,
            "claim_id": reply.claim_id or state["request"].claim_id,
        }
    )
    return {
        "request": request,
        "draft": None,
        "review": None,
        "answer": None,
        "human_decision": None,
        "questions": [],
        # New homeowner information supersedes earlier uncertainty, just like an edit.
        # Keep the full report above, and give its revised draft a fresh review budget.
        "latest_correction": reply.message,
        "revision_count": 0,
        "clarified_repair_status": reconcile_repair_status(
            reply.message, state.get("clarified_repair_status")
        ),
    }


async def commit_action(state: AgentState, runtime: Runtime[AgentContext]) -> AgentState:
    context = runtime.context
    review, decision, draft = state.get("review"), state.get("human_decision"), state.get("draft")
    if (
        state.get("phase") != "approved"
        or not review
        or review.verdict.outcome != "pass"
        or not decision
        or decision.action != "approve"
        or decision.artifact_version != state["artifact_version"]
        or review.artifact_version != state["artifact_version"]
        or not isinstance(draft, (StatusDraft, PacketDraft))
    ):
        raise ValueError("An approved, reviewed current action is required")
    claim = await load_claim(state, context)
    if claim is None or state.get("claim") is None:
        raise ValueError("A selected claim is required")
    if context.actions is None:
        raise NotImplementedError("Connect the approved-actions database/export adapter")
    result = await context.actions.commit(
        user_id=context.user_id,
        claim=state["claim"],
        proposal=draft,
        evidence=state.get("evidence", []),
        request_key=f"{state['run_id']}:{state['artifact_version']}",
    )
    return {"action_result": result, "phase": "completed"}
