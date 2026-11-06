"""Review fidelity of a proposed update to the original user message."""

from app.schemas.agents import ReviewIssue, StatusDraft

CHECKLIST = """
STATUS REVIEW:
1. Is every changed field explicitly supported by the original message or edit request?
2. Are dates, amounts, and status preserved accurately, with no invented facts?
3. Are conflicts with existing facts either explicitly corrected by the user or clarified?
4. Are insurer decisions labeled user-reported, with no claim of independent verification?
5. Are resolution comments faithful to the user's request, without silently closing the case?
Do not reassess policy coverage for a simple status update. Missing policy evidence alone
does not invalidate a factual status update. No save has occurred yet.
"""


def validate(draft: StatusDraft) -> tuple[list[ReviewIssue], list[str]]:
    # Field/status/amount validation already happens at the Pydantic boundary.
    return [], list(draft.missing_information)
