"""Run only the selected review checklist; publish coverage only after a pass."""

from langgraph.runtime import Runtime

from app.schemas.agents import (
    CoverageDraft,
    PacketDraft,
    ReviewedAnswer,
    ReviewResult,
    ReviewVerdict,
    StatusDraft,
)

from .context import AgentContext
from .evidence import EvidenceEntry, evidence_key
from .prompts import REVIEW
from .reviews import coverage, packet, status
from .state import AgentState
from .support import calculate_estimate, model_payload, retrieve_evidence


async def reviewer(state: AgentState, runtime: Runtime[AgentContext]) -> AgentState:
    context = runtime.context
    route = state["route"].route
    draft = state.get("draft")
    claim = state.get("claim")
    evidence = list(state.get("evidence", []))
    if isinstance(draft, CoverageDraft) and route == "answer_claim":
        checklist = coverage.CHECKLIST
        issues, questions = coverage.validate(draft, claim, evidence)
        assessment = draft
    elif isinstance(draft, StatusDraft) and route == "save_claim_status" and claim:
        checklist = status.CHECKLIST
        issues, questions = status.validate(draft)
        assessment = None
    elif isinstance(draft, PacketDraft) and route == "file_claim" and claim:
        checklist = packet.CHECKLIST
        issues, questions = packet.validate(
            draft, claim, evidence, context, state["request"].message
        )
        if not issues and not questions:
            issues = await packet.review_incident(
                draft,
                claim,
                state["request"].message,
                context.reviewer,
                latest_correction=state.get("latest_correction"),
            )
        if not issues and not questions and state.get("latest_correction"):
            issues = await packet.review_correction(
                draft, state["latest_correction"], context.reviewer
            )
        assessment = draft.coverage
    else:
        raise ValueError("Draft type, claim context, and review route must agree")

    if questions:
        verdict = ReviewVerdict(outcome="needs_information", issues=issues, questions=questions)
    elif issues:
        verdict = ReviewVerdict(outcome="revise", issues=issues)
    else:
        payload = model_payload(state, claim, evidence)
        if (
            isinstance(draft, PacketDraft)
            and context.prior_coverage
            and not (payload["requested_edits"] or payload.get("current_incident_statement"))
        ):
            payload["previous_reviewed_coverage"] = context.prior_coverage
        payload["draft"] = draft.model_dump(mode="json")
        payload["template"] = context.template.model_dump(mode="json")
        # Unknown coverage inputs must never be cleared just to produce an estimate.
        estimate = calculate_estimate(assessment) if assessment else None
        payload["calculated_estimate"] = estimate.model_dump(mode="json") if estimate else None
        verdict = await context.reviewer.generate(
            prompt=REVIEW + checklist,
            payload=payload,
            output_type=ReviewVerdict,
        )
        if assessment is not None and verdict.evidence_query:
            extra = await retrieve_evidence(verdict.evidence_query, context)
            evidence = list({item.chunk_id: item for item in evidence + extra}.values())
            payload = model_payload(state, claim, evidence) | {
                "draft": draft.model_dump(mode="json"),
                "template": context.template.model_dump(mode="json"),
                "calculated_estimate": estimate.model_dump(mode="json") if estimate else None,
                "additional_search_used": True,
            }
            verdict = await context.reviewer.generate(
                prompt=REVIEW
                + checklist
                + "\nNo more searches. Unresolved gaps require user input.",
                payload=payload,
                output_type=ReviewVerdict,
            )
        # Unknown evidence references cannot be accepted as a valid review.
        known_ids = {item.chunk_id for item in evidence}
        if any(set(issue.citation_ids) - known_ids for issue in verdict.issues):
            raise ValueError("Reviewer referenced evidence it was not given")

    result = ReviewResult(
        route=route,
        artifact_version=state["artifact_version"],
        verdict=verdict,
    )
    if verdict.outcome == "pass" and assessment is not None:
        key = evidence_key(
            context.user_id,
            context.policy_id,
            context.policy_version,
            claim,
            state["request"].message,
        )
        context.evidence_cache.put(
            key,
            EvidenceEntry(
                question=state["request"].message,
                passages=evidence,
                reviewed=True,
            ),
        )
    update: AgentState = {
        "review": result,
        "answer": None,
        "human_decision": None,
        "questions": verdict.questions,
        "evidence": evidence,
    }
    if verdict.outcome == "needs_information":
        update["phase"] = "needs_information"
    elif verdict.outcome == "revise":
        count = state.get("revision_count", 0)
        update["phase"] = "revision_required" if count < 1 else "blocked"
        update["revision_count"] = min(count + 1, 1)
    elif isinstance(draft, CoverageDraft):
        estimate = calculate_estimate(draft)
        update.update(
            phase="answer_ready",
            estimate=estimate,
            answer=ReviewedAnswer(
                coverage=draft,
                estimate=estimate,
                next_actions=["save_resolution", "prepare_packet"]
                if estimate and estimate.estimated_payment == 0
                else [],
            ),
        )
    else:
        update["phase"] = "human_review"
        if isinstance(draft, PacketDraft):
            update["estimate"] = calculate_estimate(draft.coverage)
    return update
