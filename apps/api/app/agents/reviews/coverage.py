"""Review support for coverage conclusions and the proposed estimate inputs."""

from app.schemas.agents import ClaimSnapshot, CoverageDraft, ReviewIssue
from app.services.rag.types import Citation

from ..support import coverage_issues

CHECKLIST = """
COVERAGE REVIEW:
1. Does each policy assertion follow from the cited passages, for this incident/cause?
2. Are relevant conditions, exclusions, endorsements, and applicable dates accounted for?
3. Are unknown facts explicitly acknowledged, without treating absent evidence as denial?
4. Are covered_amount and deductible supported? Does the policy actually allow this simple
   estimate, with no unaccounted limits, depreciation, or other adjustments?
5. Is the conclusion proportionate to evidence and distinct from a payment/insurer decision?
6. Does any payment language agree with calculated_estimate, including a zero caused by
   the deductible? Reject unsupported promised payments even if the input amounts are correct.
Missing required source passages or incident facts means needs_information.
"""


def validate(
    draft: CoverageDraft,
    claim: ClaimSnapshot | None,
    evidence: list[Citation],
) -> tuple[list[ReviewIssue], list[str]]:
    # The message can introduce a new repair amount. Its factual basis is a semantic
    # review check; the older database amount is not necessarily an upper bound.
    issues = coverage_issues(draft, evidence, None)
    questions = list(draft.missing_information)
    if not evidence:
        questions.append("Please provide relevant policy evidence before assessing coverage.")
    return issues, questions
