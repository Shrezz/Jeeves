"""Deterministic contract for the three supported Claim Companion intents.

This module does not perform any final write: the API must enforce authenticated
ownership, confirmation, approval, and package-version checks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

Intent = Literal["answer_claim", "file_claim", "save_claim_status"]


@dataclass(frozen=True)
class RouterResult:
    intent: Intent | None
    claim_id: str | None
    needs_clarification: bool
    clarification: str | None = None


def route_message(message: str, *, selected_claim_id: str | None = None) -> RouterResult:
    """Conservative fallback router; clarify uncertain or conflicting requests.

    Keep the explicit selected case: never guess between multiple claims.
    """
    text = message.strip().lower()
    if not text:
        return RouterResult(None, selected_claim_id, True, "What would you like help with?")
    status = bool(re.search(
        r"\b(update (?:my |the )?(?:claim )?status|status update|"
        r"repair (?:is |was )?(?:complete|completed|finished)|"
        r"insurer (?:asked|requested|said)|upload status)\b", text
    ))
    filing = bool(re.search(
        r"\b(file (?:a |my |the )?claim|filing a claim|"
        r"prepare (?:a |my |the )?claim|prepare (?:a |the )?packet|"
        r"submit (?:a |my |the )?claim|let'?s file)\b", text
    ))
    if status and filing:
        return RouterResult(None, selected_claim_id, True,
                            "Would you like to update the existing claim first, or prepare a packet?")
    if status:
        if not selected_claim_id:
            return RouterResult("save_claim_status", None, True,
                                "Which claim should I update?")
        return RouterResult("save_claim_status", selected_claim_id, False)
    if filing:
        return RouterResult("file_claim", selected_claim_id, False)
    question = bool(re.search(
        r"\b(cover(?:ed|age)?|deductible|policy|exclude(?:d|s)?|"
        r"eligible|is it|can i|what|why|how|does|do i)\b", text
    )) or text.endswith("?")
    if question:
        return RouterResult("answer_claim", selected_claim_id, False)
    return RouterResult(None, selected_claim_id, True,
                        "Do you want to ask about coverage, prepare a claim, or update a claim status?")


def estimate_payment(eligible_loss: str | int | Decimal, deductible: str | int | Decimal) -> Decimal:
    """Code-owned estimate; never let a model invent payment arithmetic."""
    try:
        loss = Decimal(str(eligible_loss))
        excess = Decimal(str(deductible))
    except InvalidOperation as exc:
        raise ValueError("Loss and deductible must be numeric") from exc
    if not loss.is_finite() or not excess.is_finite() or loss < 0 or excess < 0:
        raise ValueError("Loss and deductible must be nonnegative finite amounts")
    return max(Decimal("0"), loss - excess).quantize(Decimal("0.01"))
