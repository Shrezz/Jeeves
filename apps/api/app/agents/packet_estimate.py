"""Read the explicit flat-deductible formula used by the synthetic demo policies."""

import re
from dataclasses import dataclass
from decimal import Decimal

from app.schemas.agents import PacketDraft
from app.services.rag.types import Citation

_MONEY = r"\$((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?)"
_FORMULA = re.compile(
    r"estimated payment for an eligible loss\s+max\(0,\s*min\(eligible expense,\s*"
    + _MONEY
    + r"\)\s*[-−]\s*"
    + _MONEY
    + r"\)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FlatTerms:
    limit: Decimal
    deductible: Decimal
    citation_id: str

    def apply(self, draft: PacketDraft) -> PacketDraft:
        cost = draft.facts.repair_cost
        if cost is None or draft.coverage.conclusion == "likely_not_covered":
            return draft
        coverage = draft.coverage.model_copy(
            update={
                "covered_amount": min(cost, self.limit),
                "deductible": self.deductible,
                "citation_ids": list(
                    dict.fromkeys([*draft.coverage.citation_ids, self.citation_id])
                ),
            }
        )
        return draft.model_copy(update={"coverage": coverage})


def explicit_flat_terms(evidence: list[Citation]) -> FlatTerms | None:
    # Match the operative formula, never the dollar figures in illustrative examples.
    # Unrecognized or conflicting formulae stay with the ordinary review workflow.
    matches = {}
    for cite in evidence:
        operative = re.split(
            r"\billustrative calculations\b", cite.excerpt, maxsplit=1, flags=re.IGNORECASE
        )[0]
        for limit, deductible in _FORMULA.findall(operative):
            terms = Decimal(limit.replace(",", "")), Decimal(deductible.replace(",", ""))
            matches.setdefault(terms, cite.chunk_id)
    if len(matches) == 1:
        (cap, deductible), source = next(iter(matches.items()))
        return FlatTerms(cap, deductible, source)
    return None
