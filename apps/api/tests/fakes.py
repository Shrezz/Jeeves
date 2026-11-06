"""Explicit test doubles: no embeddings, live LLM calls, or database writes."""

from dataclasses import dataclass, field
from typing import Any

from app.agents.context import AgentContext, Output
from app.agents.state import AgentState
from app.schemas.agents import (
    AgentRequest,
    ClaimSnapshot,
    CoverageDraft,
    IncidentFacts,
    PacketDraft,
    RouteDecision,
)
from app.services.rag.types import Citation


@dataclass
class ScriptedModel:
    outputs: list[Any] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def generate(
        self, *, prompt: str, payload: dict[str, Any], output_type: type[Output]
    ) -> Output:
        self.calls.append({"prompt": prompt, "payload": payload, "output_type": output_type})
        if not self.outputs:
            raise AssertionError("Unexpected model call")
        result = self.outputs.pop(0)
        if isinstance(result, Exception):
            raise result
        return output_type.model_validate(result)


@dataclass
class FixtureClaims:
    claim: ClaimSnapshot

    async def load_claim(self, *, user_id: str, claim_id: str) -> ClaimSnapshot:
        return self.claim  # Nodes must still reject a buggy adapter returning the wrong owner.


@dataclass
class FixturePolicies:
    evidence: list[Citation]
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def retrieve_evidence(self, **kwargs: Any) -> list[Citation]:
        self.calls.append(kwargs)
        return self.evidence


def make_context() -> AgentContext:
    return AgentContext(
        user_id="demo-user",
        policy_id="demo-policy",
        policy_version="v1",
        generator=ScriptedModel(),
        reviewer=ScriptedModel(),
        claims=FixtureClaims(
            ClaimSnapshot(
                claim_id="window",
                user_id="demo-user",
                policy_id="demo-policy",
                policy_version="v1",
                version=1,
                facts=IncidentFacts(
                    description="A window broke during a storm.",
                    cause="Windborne debris",
                    occurred_on="2026-11-01",
                    repair_cost="150.00",
                ),
                attachment_ids=["receipt-1"],
            )
        ),
        policies=FixturePolicies(
            [
                Citation(
                    chunk_id="wind-clause",
                    policy_id="demo-policy",
                    policy_version="v1",
                    page=2,
                    section="Synthetic wind coverage",
                    score=0.9,
                    excerpt="DEMO ONLY: Windborne debris damage is covered, with a $1,000 flat deductible.",
                )
            ]
        ),
    )


def make_state(route: str = "answer_claim", **request_changes: Any) -> AgentState:
    request = {"message": "Is my broken window covered?", "claim_id": "window"}
    request.update(request_changes)
    return {
        "request": AgentRequest.model_validate(request),
        "route": RouteDecision(route=route),
        "revision_count": 0,
    }


def coverage_draft(**changes: Any) -> CoverageDraft:
    values = {
        "conclusion": "likely_covered",
        "explanation": "The cited demo wind clause may apply.",
        "citation_ids": ["wind-clause"],
        "covered_amount": "150.00",
        "deductible": "1000.00",
    }
    values.update(changes)
    return CoverageDraft.model_validate(values)


def packet_draft(context: AgentContext, **changes: Any) -> PacketDraft:
    values = {
        "narrative": "A storm broke the window. Repair cost was $150.",
        "facts": context.claims.claim.facts,
        "coverage": coverage_draft(),
        "attachment_ids": ["receipt-1"],
    }
    values.update(changes)
    return PacketDraft.model_validate(values)
