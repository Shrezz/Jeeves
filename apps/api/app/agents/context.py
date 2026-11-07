"""Small injectable boundaries for models, policy retrieval, and claim reads."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from app.schemas.agents import ActionResult, ClaimSnapshot, ClaimTemplate, PacketDraft, StatusDraft
from app.services.rag.types import Citation

from .evidence import EvidenceCache

Output = TypeVar("Output", bound=BaseModel)


class StructuredModel(Protocol):
    async def generate(
        self,
        *,
        prompt: str,
        payload: dict[str, Any],
        output_type: type[Output],
    ) -> Output:
        """Return validated structured output, or raise on invalid/unavailable output."""


class ClaimReader(Protocol):
    async def load_claim(self, *, user_id: str, claim_id: str) -> ClaimSnapshot:
        """Load an owned claim; raise if missing or inaccessible."""


class PolicyReader(Protocol):
    async def retrieve_evidence(
        self,
        *,
        user_id: str,
        policy_id: str,
        question: str,
        limit: int,
    ) -> Sequence[Citation]:
        """Retrieve full relevant passages, scoped to this owner and policy."""


class ApprovedActions(Protocol):
    async def commit(
        self,
        *,
        user_id: str,
        claim: ClaimSnapshot,
        proposal: StatusDraft | PacketDraft,
        evidence: list[Citation],
        request_key: str,
    ) -> ActionResult:
        """Atomically enforce owner/version, deduplicate request_key, and save/export.

        Persist approved packet facts/evidence and its artifact reference together.
        A replay returns the first result; a conflicting version raises.
        """


@dataclass(frozen=True)
class AgentContext:
    # Resolve these from authenticated, authorized backend context, not model output.
    user_id: str
    policy_id: str
    policy_version: str
    generator: StructuredModel
    reviewer: StructuredModel
    claims: ClaimReader
    policies: PolicyReader
    template: ClaimTemplate = field(default_factory=ClaimTemplate)
    evidence_cache: EvidenceCache = field(default_factory=EvidenceCache)
    actions: ApprovedActions | None = None
    prior_coverage: dict[str, Any] | None = None
