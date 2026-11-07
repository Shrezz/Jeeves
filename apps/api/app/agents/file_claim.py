"""Prepare packet content and evidence. This node never submits or exports a claim."""

import re

from langgraph.runtime import Runtime

from app.schemas.agents import PacketDraft

from .context import AgentContext
from .named_peril import apply_named_cause
from .packet_estimate import explicit_flat_terms
from .prompts import PACKET, RESTATED_PACKET
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
    if context.prior_coverage and not (
        payload["requested_edits"] or payload.get("current_incident_statement")
    ):
        payload["previous_reviewed_coverage"] = context.prior_coverage
    payload["available_chunk_ids"] = [item.chunk_id for item in evidence]
    terms = explicit_flat_terms(evidence)
    if terms:
        payload["conditional_payment_rule"] = {
            "source": terms.citation_id,
            "flat_deductible": str(terms.deductible),
            "eligible_expense_limit": str(terms.limit),
            "meaning": "If eligible, the server will apply this formula to the reported repair expense. Explain the conditional calculation even when the policy peril is unresolved.",
        }
    payload["attachment_inventory"] = {
        "uploaded_ids": claim.attachment_ids,
        "note": "This is the complete list. An empty list means no files have been uploaded.",
    }
    draft = await context.generator.generate(
        prompt=RESTATED_PACKET if payload.get("current_incident_statement") else PACKET,
        payload=payload,
        output_type=PacketDraft,
    )
    # When the homeowner explicitly supplies a quoted statement for this packet,
    # preserve it word-for-word instead of asking the model to paraphrase it.
    # Do not reuse an older quotation after a subsequent edit or clarification.
    if statement := payload.get("current_incident_statement"):
        draft = draft.model_copy(update={"narrative": f"Homeowner statement: “{statement}”"})
        draft = apply_named_cause(draft, statement, evidence)
    clarified_status = state.get("clarified_repair_status")
    if clarified_status:
        # Preserve the explicit answer and remove only this redundant question.
        redundant = re.compile(
            r"^(?:the )?repair status is unknown(?:; confirmation of completion or pending status is needed)?[.!?]?$",
            re.IGNORECASE,
        )
        draft = draft.model_copy(
            update={
                "facts": draft.facts.model_copy(update={"repair_status": clarified_status}),
                "coverage": draft.coverage.model_copy(
                    update={
                        "missing_information": [
                            q
                            for q in draft.coverage.missing_information
                            if not redundant.fullmatch(q.strip())
                        ]
                    }
                ),
                "missing_information": [
                    q for q in draft.missing_information if not redundant.fullmatch(q.strip())
                ],
            }
        )
    if terms:
        draft = terms.apply(draft)
    return draft_update(
        state,
        draft=draft,
        claim=claim,
        evidence=evidence,
        estimate=calculate_estimate(draft.coverage),
    )
