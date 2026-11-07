"""Preserve only explicit repair-status corrections from the user."""

import re
from typing import Literal

RepairUpdate = Literal["pending", "scheduled", "completed"]
_STATEMENT = re.compile(
    r"\brepairs?\s+(?:(?:is|are|was|were|has been|have been|remains|remain|still)\s+)*"
    r"(?P<neg>not\s+(?:yet\s+)?|no\s+longer\s+)?"
    r"(?P<status>pending|scheduled|completed|complete|finished)\b",
    re.IGNORECASE,
)
_CONTRADICTORY = re.compile(
    r"\brepairs?\b[^.!?]{0,50}\b(?:pending|scheduled|completed|complete|finished)\b"
    r"\s+(?:but|and)\s+(?:also\s+|now\s+)?(?:pending|scheduled|completed|complete|finished)\b",
    re.IGNORECASE,
)


def reconcile_repair_status(text: str, previous: RepairUpdate | None) -> RepairUpdate | None:
    """Use a clear latest correction; never guess from ambiguous or negated text."""
    if _CONTRADICTORY.search(text):
        return None
    positive: set[RepairUpdate] = set()
    negated: set[RepairUpdate] = set()
    for match in _STATEMENT.finditer(text):
        status: RepairUpdate = (
            "completed"
            if match["status"].lower() in {"completed", "complete", "finished"}
            else match["status"].lower()
        )
        (negated if match["neg"] else positive).add(status)
    if len(positive) > 1 or positive & negated:
        return None
    if positive:
        return next(iter(positive))
    if previous in negated:
        return None
    return previous
