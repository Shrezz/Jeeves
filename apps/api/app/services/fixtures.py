"""Explicit synthetic adapters for local UI integration; not live RAG or a production database."""

import asyncio
import hashlib
import html
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.agents.context import AgentContext, Output
from app.agents.evidence import EvidenceCache
from app.schemas.agents import (
    ActionResult,
    ClaimSnapshot,
    CoverageDraft,
    EvidencePlan,
    IncidentFacts,
    PacketDraft,
    ReviewVerdict,
    RouteDecision,
    StatusDraft,
)
from app.services.rag.types import Citation


@dataclass(frozen=True)
class Artifact:
    owner_id: str
    content: bytes
    filename: str = "claim-packet.html"
    media_type: str = "text/html"


@dataclass
class FixtureStore:
    claims: dict[str, ClaimSnapshot] = field(default_factory=dict)
    artifacts: dict[str, Artifact] = field(default_factory=dict)
    results: dict[str, tuple[str, str, ActionResult]] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    cache: EvidenceCache = field(default_factory=EvidenceCache)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @classmethod
    def seeded(cls):
        store = cls()
        store.claims["demo-window"] = ClaimSnapshot(
            claim_id="demo-window",
            user_id="demo-user",
            policy_id="demo-policy",
            policy_version="v1",
            version=1,
            facts=IncidentFacts(
                description="A window broke during a storm.",
                cause="Windborne debris",
                occurred_on=date(2026, 11, 1),
            ),
        )
        return store

    async def load_claim(self, *, user_id: str, claim_id: str) -> ClaimSnapshot:
        claim = self.claims.get(claim_id)
        if not claim or claim.user_id != user_id:
            raise PermissionError("Claim not found")
        return claim.model_copy(deep=True)

    async def retrieve_evidence(
        self, *, user_id: str, policy_id: str, question: str, limit: int
    ) -> list[Citation]:
        if user_id != "demo-user" or policy_id != "demo-policy":
            raise PermissionError("Policy not found")
        return [
            Citation(
                chunk_id="demo-wind",
                policy_id="demo-policy",
                policy_version="v1",
                page=2,
                section="Synthetic policy — wind and exclusions",
                score=1.0,
                excerpt="DEMO POLICY: Windborne debris damaging a dwelling window is covered. "
                "A flat $1,000 deductible applies. Wear and tear is excluded. "
                "For this synthetic example only, no other limits or depreciation apply.",
            )
        ][:limit]

    async def commit(
        self,
        *,
        user_id: str,
        claim: ClaimSnapshot,
        proposal: StatusDraft | PacketDraft,
        evidence: list[Citation],
        request_key: str,
    ) -> ActionResult:
        fingerprint = hashlib.sha256(
            (claim.claim_id + proposal.model_dump_json()).encode()
        ).hexdigest()
        async with self.lock:
            if request_key in self.results:
                owner, previous, result = self.results[request_key]
                if owner != user_id or previous != fingerprint:
                    raise ValueError("Conflicting action replay")
                return result
            current = await self.load_claim(user_id=user_id, claim_id=claim.claim_id)
            if current.version != claim.version:
                raise ValueError("Claim version conflict")
            updates = proposal.facts.model_dump(exclude_none=True)
            facts = IncidentFacts.model_validate(current.facts.model_dump() | updates)
            changes = {"version": current.version + 1, "facts": facts}
            artifact_id = None
            if isinstance(proposal, StatusDraft):
                changes.update(
                    status=proposal.status or current.status, notes=current.notes + [proposal.note]
                )
            else:
                artifact_id = str(uuid4())
                fields = "".join(
                    f"<dt>{html.escape(k)}</dt><dd>{html.escape(str(v))}</dd>"
                    for k, v in facts.model_dump(mode="json").items()
                )
                sources = "".join(
                    f"<li>Page {p.page}: {html.escape(p.excerpt)}</li>" for p in evidence
                )
                content = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<title>Synthetic claim packet</title><style>body{{font:16px system-ui;max-width:760px;margin:48px auto;
color:#173b38;line-height:1.6}}dt{{font-weight:bold}}dd{{margin:0 0 12px}}aside{{background:#fff3d5;padding:12px}}
</style><h1>Homeowners claim packet</h1><aside>DEMO — Prepared for human use. Not submitted to an insurer.
This is a synthetic packet, not an official insurer form.</aside><h2>Incident</h2><dl>{fields}</dl>
<p>{html.escape(proposal.narrative)}</p><h2>Policy assessment</h2>
<p>{html.escape(proposal.coverage.explanation)}</p><h2>Policy evidence</h2><ul>{sources}</ul>
<h2>Attachment references</h2><p>{html.escape(", ".join(proposal.attachment_ids) or "None supplied")}</p></html>"""
                self.artifacts[artifact_id] = Artifact(user_id, content.encode())
            updated = ClaimSnapshot.model_validate(current.model_dump() | changes)
            self.claims[claim.claim_id] = updated
            result = ActionResult(
                outcome="prepared" if artifact_id else "saved",
                claim_id=claim.claim_id,
                claim_version=updated.version,
                artifact_id=artifact_id,
                mode="fixture",
            )
            self.results[request_key] = (user_id, fingerprint, result)
            self.events.append(
                {
                    "request_key": request_key,
                    "result": result.model_dump(mode="json"),
                    "proposal": proposal.model_dump(mode="json"),
                }
            )
            return result

    async def read_artifact(self, user_id: str, artifact_id: str) -> Artifact:
        artifact = self.artifacts.get(artifact_id)
        if not artifact or artifact.owner_id != user_id:
            raise PermissionError("Artifact not found")
        return artifact


class FixtureModel:
    """Deterministic demo script. Its responses are not evidence of model accuracy."""

    async def generate(
        self, *, prompt: str, payload: dict[str, Any], output_type: type[Output]
    ) -> Output:
        message = payload.get("request", {})
        message = message.get("message", "") if isinstance(message, dict) else message
        lower = message.lower()
        claim = payload.get("confirmed_claim") or {}
        facts = IncidentFacts.model_validate(claim.get("facts", {}))
        amounts = re.findall(r"\$\s*(\d+(?:\.\d{1,2})?)", message)
        if amounts:
            facts = facts.model_copy(update={"repair_cost": Decimal(amounts[-1])})
        if "wear" in lower:
            facts = facts.model_copy(update={"cause": "Wear and tear"})
        elif "wind" in lower or "storm" in lower:
            facts = facts.model_copy(update={"cause": "Windborne debris"})
        if output_type is RouteDecision:
            route = (
                "file_claim"
                if any(w in lower for w in ("file", "packet", "prepare"))
                else "save_claim_status"
                if any(w in lower for w in ("save", "update", "paid", "resolved"))
                else "answer_claim"
                if any(w in lower for w in ("cover", "deductible", "window"))
                else None
            )
            return RouteDecision(
                route=route,
                clarification=None if route else "Would you like coverage, an update, or a packet?",
            )
        if output_type is EvidencePlan:
            prior = payload.get("previous_question", "").lower()
            reuse = not any(
                w in lower and w not in prior for w in ("wear", "flood", "earthquake", "fire")
            )
            return EvidencePlan(reuse=reuse, query=None if reuse else message)
        if output_type is ReviewVerdict:
            return ReviewVerdict(outcome="pass")
        if output_type is StatusDraft:
            return StatusDraft(
                note=message,
                status="resolved" if "resolv" in lower else "repaired" if amounts else None,
                facts=IncidentFacts(repair_cost=facts.repair_cost) if amounts else IncidentFacts(),
            )
        evidence = payload.get("evidence", [])
        unknown = facts.cause is None or not evidence
        covered = bool(facts.cause and "wind" in facts.cause.lower())
        assessment = CoverageDraft(
            conclusion="unclear"
            if unknown
            else "likely_covered"
            if covered
            else "likely_not_covered",
            explanation="The synthetic wind clause may apply. The $1,000 deductible is subtracted from covered repair costs."
            if covered
            else "The synthetic wear-and-tear exclusion may apply."
            if not unknown
            else "More incident or policy information is needed.",
            citation_ids=[evidence[0]["chunk_id"]] if evidence else [],
            missing_information=["What caused the window damage?"] if unknown else [],
            covered_amount=facts.repair_cost if covered else None,
            deductible=Decimal("1000.00") if covered else None,
        )
        if output_type is CoverageDraft:
            return assessment
        if output_type is PacketDraft:
            return PacketDraft(
                narrative="User reports: " + message,
                facts=facts,
                coverage=assessment,
                attachment_ids=claim.get("attachment_ids", []),
            )
        raise ValueError("Unsupported fixture output type")


def fixture_context(store: FixtureStore, generator=None, reviewer=None):
    async def resolve(user_id: str, policy_id: str, claim_id: str | None) -> AgentContext:
        if user_id != "demo-user" or policy_id != "demo-policy":
            raise PermissionError("Policy not found")
        if claim_id:
            await store.load_claim(user_id=user_id, claim_id=claim_id)
        return AgentContext(
            user_id=user_id,
            policy_id=policy_id,
            policy_version="v1",
            generator=generator or FixtureModel(),
            reviewer=reviewer or FixtureModel(),
            claims=store,
            policies=store,
            actions=store,
            evidence_cache=store.cache,
        )

    return resolve
