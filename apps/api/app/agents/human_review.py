"""Pause for an authenticated human decision. Final writes belong to a later action node."""

from langgraph.runtime import Runtime
from langgraph.types import interrupt

from app.schemas.agents import HumanDecision

from .context import AgentContext
from .state import AgentState
from .support import load_claim


async def human_review(state: AgentState, runtime: Runtime[AgentContext]) -> AgentState:
    review = state.get("review")
    draft = state.get("draft")
    if (
        review is None
        or draft is None
        or review.verdict.outcome != "pass"
        or review.artifact_version != state["artifact_version"]
        or review.route != state["route"].route
        or review.route == "answer_claim"
    ):
        raise ValueError("Human approval requires a current, passed action review")

    # The node restarts on resume. Keep everything before interrupt side-effect free.
    response = interrupt(
        {
            "kind": "human_review",
            "route": review.route,
            "artifact_version": state["artifact_version"],
            "draft": draft.model_dump(mode="json"),
            "estimate": state["estimate"].model_dump(mode="json")
            if state.get("estimate")
            else None,
            "actions": ["approve", "edit", "reject"],
        }
    )
    decision = HumanDecision.model_validate(response)
    if decision.artifact_version != state["artifact_version"]:
        raise ValueError("This decision belongs to an older artifact version")
    current_claim = await load_claim(state, runtime.context)
    original_claim = state.get("claim")
    if (
        current_claim is None
        or original_claim is None
        or current_claim.version != original_claim.version
    ):
        raise ValueError("The claim changed while awaiting review; refresh and review again")

    if decision.action == "edit":
        return {
            "request": state["request"].model_copy(
                update={
                    "message": state["request"].message + "\nUser edit: " + decision.feedback,
                }
            ),
            "human_decision": decision,
            "review": None,
            "answer": None,
            "revision_count": 0,
            "phase": "revision_required",
        }
    return {
        "human_decision": decision,
        "phase": "approved" if decision.action == "approve" else "rejected",
    }
