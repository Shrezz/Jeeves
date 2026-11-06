"""Prepare a proposed update; persistence happens in a later approved backend action."""

from langgraph.runtime import Runtime

from app.schemas.agents import StatusDraft

from .context import AgentContext
from .prompts import STATUS
from .state import AgentState
from .support import draft_update, load_claim, model_payload


async def save_claim_status(state: AgentState, runtime: Runtime[AgentContext]) -> AgentState:
    context = runtime.context
    claim = await load_claim(state, context)
    if claim is None:
        return {
            "phase": "needs_information",
            "questions": ["Which claim should I update?"],
            "draft": None,
            "answer": None,
            "review": None,
            "human_decision": None,
        }
    draft = await context.generator.generate(
        prompt=STATUS,
        payload=model_payload(state, claim, []),
        output_type=StatusDraft,
    )
    return draft_update(state, draft=draft, claim=claim, evidence=[])
