"""A bounded, owner/policy/incident-scoped cache. It never caches approval decisions."""

import hashlib
import json
from dataclasses import dataclass, field

from app.schemas.agents import ClaimSnapshot
from app.services.rag.types import Citation


@dataclass
class EvidenceEntry:
    question: str
    passages: list[Citation]
    reviewed: bool = False


@dataclass
class EvidenceCache:
    entries: dict[str, EvidenceEntry] = field(default_factory=dict)
    max_entries: int = 128

    def put(self, key: str, entry: EvidenceEntry) -> None:
        if key not in self.entries and len(self.entries) >= self.max_entries:
            self.entries.pop(next(iter(self.entries)))
        self.entries[key] = entry


def evidence_key(
    user_id: str, policy_id: str, version: str, claim: ClaimSnapshot | None, message: str
) -> str:
    # Amount changes require recalculation/review, but do not alone invalidate source passages.
    facts = claim.facts.model_dump(mode="json", exclude={"repair_cost"}) if claim else message
    scope = [user_id, policy_id, version, claim.claim_id if claim else None, facts]
    return hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()
