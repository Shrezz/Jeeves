"""Bounded arithmetic illustrations, not coverage or insurer payment decisions."""

import re
from decimal import Decimal, InvalidOperation

# Support only an explicit flat, per-occurrence deductible. Percentage,
# peril-specific, aggregate and ambiguous terms do not qualify.
_FLAT = re.compile(
    r"\bflat\s+deductible\s*[:\-]?\s*\$((?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.\d{2})?)\s+per\s+covered\s+occurrence\b",
    re.IGNORECASE,
)
_WIND = re.compile(
    r"sudden impact from windborne debris that breaks an exterior dwelling window is a covered cause of loss\.",
    re.IGNORECASE,
)


def flat_deductible(passages: list[dict]) -> tuple[Decimal, dict] | None:
    matches = []
    for passage in passages:
        excerpt = passage.get("excerpt", "")
        if not isinstance(excerpt, str):
            continue
        for match in _FLAT.finditer(excerpt):
            try:
                value = Decimal(match.group(1).replace(",", ""))
            except InvalidOperation:
                continue
            if value.is_finite() and value >= 0:
                matches.append((value, {**passage, "excerpt": match.group(0)}))
    if not matches or len({item[0] for item in matches}) != 1:
        return None
    return matches[0]


def recorded_amount(value) -> Decimal | None:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return amount if amount.is_finite() and amount > 0 else None


def illustrated_payment(amount: Decimal, deductible: Decimal) -> Decimal:
    return max(Decimal("0.00"), amount - deductible)


def cited_wind_term(question: str, passages: list[dict]) -> dict | None:
    if not re.search(r"\bwindborne\s+debris\b", question, re.IGNORECASE) or not re.search(
        r"\bwindows?\b", question, re.IGNORECASE
    ):
        return None
    for passage in passages:
        excerpt = passage.get("excerpt", "")
        match = _WIND.search(excerpt) if isinstance(excerpt, str) else None
        if match:
            return {**passage, "excerpt": match.group(0)}
    return None
