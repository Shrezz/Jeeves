"""Draft a grounded coverage answer. Only the reviewer can publish it to `answer`."""

from langgraph.runtime import Runtime

from app.schemas.agents import CoverageDraft

from .context import AgentContext
from .prompts import ANSWER
from .state import AgentState
from .support import calculate_estimate, draft_update, load_claim, model_payload, policy_evidence


async def answer_claim(state: AgentState, runtime: Runtime[AgentContext]) -> AgentState:
    context = runtime.context
    claim = await load_claim(state, context)
    evidence = await policy_evidence(state, context, claim)
    draft = await context.generator.generate(
        prompt=ANSWER,
        payload=model_payload(state, claim, evidence),
        output_type=CoverageDraft,
    )
    return draft_update(
        state,
        draft=draft,
        claim=claim,
        evidence=evidence,
        estimate=calculate_estimate(draft),
    )
