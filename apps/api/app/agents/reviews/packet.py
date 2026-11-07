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
6. Are receipt/attachment references real? Does it avoid claiming insurer submission or acceptance?
The template's required facts are incident description, cause, date, and reported repair cost.
The homeowner's earlier notes are incident facts; the latest filing request need not repeat them.
Distinguish missing facts from optional supporting documents. If a generator's
missing_information asks only for receipt upload/verification, a draft clearly labeled
user-reported can PASS; those requests are reminders for the homeowner. The draft need
not contain a literal disclaimer: the interface labels it Not submitted. Unresolved
material cause, cost or policy gaps must still be clarified. Treat any calculated estimate
as conditional on the reported facts; pass only if the inputs and arithmetic are supported.
Assess the whole packet including the server's calculated_estimate, displayed beside the
narrative. Do not require the narrative to repeat its amounts. Use the household's explicit
reports as conditional inputs, not hypotheticals that must be externally verified. A missing
receipt upload does not make the reported date, cause, location or repair cost unknown.
When previous_reviewed_coverage is supplied, check it against the original passages; a
filing request alone changes neither the reported facts nor the policy. Request revision
for material factual or policy errors, not for wording preferences.
A conditional estimate based on reported eligible expenses is appropriate. Zero estimated
payment is not a reason to reject preparation. Explain the deductible.
"""


def validate(
    draft: PacketDraft,
    claim: ClaimSnapshot,
    evidence: list[Citation],
    context: AgentContext,
) -> tuple[list[ReviewIssue], list[str]]:
    issues = coverage_issues(draft.coverage, evidence, draft.facts.repair_cost)
    if (
        draft.coverage.conclusion == "likely_covered"
        and draft.facts.repair_cost
        and draft.coverage.covered_amount == 0
        and draft.coverage.deductible
    ):
        issues.append(
            ReviewIssue(
                check="gross_expense",
                field="coverage.covered_amount",
                detail="Covered amount is the eligible repair expense before the deductible, not the estimated payout. Use the supported gross expense, or null if uncertain.",
            )
        )
    if set(draft.attachment_ids) - set(claim.attachment_ids):
        issues.append(
            ReviewIssue(
                check="attachment_exists",
                field="attachment_ids",
                detail="The packet refers to an attachment not present on the claim.",
            )
        )
    # Only deterministic omissions can short-circuit the independent reviewer. It
    # decides whether the generator's other questions actually block a review draft.
    questions = missing_fields(draft, context)
    if not evidence:
        questions.append("Please provide relevant policy evidence before preparing the packet.")
    return issues, questions
