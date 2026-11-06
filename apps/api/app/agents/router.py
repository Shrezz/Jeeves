"""Classify intent while preserving the original message for the selected agent."""

from langgraph.runtime import Runtime

from app.schemas.agents import RouteDecision

from .context import AgentContext
from .prompts import ROUTER
from .state import AgentState


async def router(state: AgentState, runtime: Runtime[AgentContext]) -> AgentState:
    request = state["request"]
    decision = (
        RouteDecision(route=request.explicit_route)
        if request.explicit_route
        else await runtime.context.generator.generate(
            prompt=ROUTER,
            payload={"request": request.model_dump(mode="json")},
            output_type=RouteDecision,
        )
    )
    return {
        "route": decision,
        "phase": "routed" if decision.route else "needs_information",
        "questions": [decision.clarification] if decision.clarification else [],
    }
