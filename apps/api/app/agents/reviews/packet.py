"""Review packet completeness, factual consistency, and policy support."""

from app.schemas.agents import ClaimSnapshot, PacketDraft, ReviewIssue
from app.services.rag.types import Citation

from ..context import AgentContext
from ..support import coverage_issues, missing_fields

CHECKLIST = """
PACKET REVIEW:
1. Are template requirements present or explicitly identified as missing?
2. Does the narrative match structured facts, repair amounts, dates, and existing attachments?
3. Are changes from the confirmed claim explicitly supported by the user's message/edits?
4. Does the coverage assessment follow the cited policy, including relevant exclusions and
   conditions? Are missing evidence and uncertainty clearly expressed?
5. Are estimate inputs supported and appropriate for a simple flat-deductible calculation?
   Does any payment language match calculated_estimate, including the deductible explanation?
6. Are receipt/attachment references real? Does it say prepared, never submitted or accepted?
Zero estimated payment is not a reason to reject preparation. Explain the deductible.
"""


def validate(
    draft: PacketDraft,
    claim: ClaimSnapshot,
    evidence: list[Citation],
    context: AgentContext,
) -> tuple[list[ReviewIssue], list[str]]:
    issues = coverage_issues(draft.coverage, evidence, draft.facts.repair_cost)
    if set(draft.attachment_ids) - set(claim.attachment_ids):
        issues.append(
            ReviewIssue(
                check="attachment_exists",
                field="attachment_ids",
                detail="The packet refers to an attachment not present on the claim.",
            )
        )
    questions = list(
        dict.fromkeys(
            draft.missing_information
            + draft.coverage.missing_information
            + missing_fields(draft, context)
        )
    )
    if not evidence:
        questions.append("Please provide relevant policy evidence before preparing the packet.")
    return issues, questions
