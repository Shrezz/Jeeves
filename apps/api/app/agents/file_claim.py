"""Prepare packet content and evidence. This node never submits or exports a claim."""

from langgraph.runtime import Runtime

from app.schemas.agents import PacketDraft

from .context import AgentContext
from .prompts import PACKET
from .state import AgentState
from .support import calculate_estimate, draft_update, load_claim, model_payload, policy_evidence


async def file_claim(state: AgentState, runtime: Runtime[AgentContext]) -> AgentState:
    context = runtime.context
    claim = await load_claim(state, context)
    if claim is None:
        return {
            "phase": "needs_information",
            "questions": ["Which claim should I prepare?"],
            "draft": None,
            "answer": None,
            "review": None,
            "human_decision": None,
        }
    evidence = await policy_evidence(state, context, claim)
    payload = model_payload(state, claim, evidence)
    payload["template"] = context.template.model_dump(mode="json")
    if context.prior_coverage:
        payload["previous_reviewed_coverage"] = context.prior_coverage
    payload["available_chunk_ids"] = [item.chunk_id for item in evidence]
    payload["attachment_inventory"] = {
        "uploaded_ids": claim.attachment_ids,
        "note": "This is the complete list. An empty list means no files have been uploaded.",
    }
    draft = await context.generator.generate(
        prompt=PACKET, payload=payload, output_type=PacketDraft
    )
    return draft_update(
        state,
        draft=draft,
        claim=claim,
        evidence=evidence,
        estimate=calculate_estimate(draft.coverage),
    )
