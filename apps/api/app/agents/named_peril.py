"""Match an affirmative homeowner statement to this synthetic form's enumerated causes."""

import re

from app.schemas.agents import PacketDraft
from app.services.rag.types import Citation


def apply_named_cause(draft: PacketDraft, statement: str, evidence: list[Citation]) -> PacketDraft:
    # Only match a complete affirmative sentence to a verbatim listed alternative.
    # A question, a negation, a policy quote, or a merely similar term is insufficient.
    if draft.coverage.conclusion == "likely_not_covered":
        return draft
    for passage in evidence:
        listed = re.search(
            r"2\.2 Covered causes\s+Covered causes are ([^.]+)\.", passage.excerpt, re.I
        )
        if not listed:
            continue
        for term in re.split(r",\s*(?:and\s+)?", listed[1]):
            short = term.removeprefix("impact by ")
            if not re.search(
                r"(?:^|[.!]\s+)It was " + re.escape(short) + r"[.!](?:\s|$)", statement, re.I
            ):
                continue
            # The match establishes the named cause only. The normal independent policy
            # reviewer must still check every other condition and exclusion before display.
            assessment = (
                f"The homeowner reports {short}. This matches the listed cause “{term}” "
                f"in §2.2 ({passage.chunk_id}). On this account the cause appears covered. "
                "Eligibility for this window and expense remains subject to the policy conditions, "
                "exclusions, endorsements and insurer review."
            )

            def unrelated(question: str) -> bool:
                return short.casefold() not in question.casefold() and not (
                    "branch" in question.lower()
                    and any(w in question.lower() for w in ("debris", "sudden", "windstorm"))
                )

            cov = draft.coverage.model_copy(
                update={
                    "explanation": assessment,
                    "conclusion": "likely_covered",
                    "citation_ids": list(
                        dict.fromkeys([passage.chunk_id, *draft.coverage.citation_ids])
                    ),
                    "missing_information": [
                        q for q in draft.coverage.missing_information if unrelated(q)
                    ],
                }
            )
            return draft.model_copy(
                update={
                    "coverage": cov,
                    "facts": draft.facts.model_copy(update={"cause": short}),
                    "missing_information": [q for q in draft.missing_information if unrelated(q)],
                }
            )
    return draft
