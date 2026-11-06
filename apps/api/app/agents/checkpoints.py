"""Explicit checkpoint serialization allowlist for application-owned contract types."""

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer


def checkpoint_serializer() -> JsonPlusSerializer:
    names = (
        "AgentRequest",
        "RouteDecision",
        "IncidentFacts",
        "ClaimSnapshot",
        "CoverageDraft",
        "StatusDraft",
        "PacketDraft",
        "PaymentEstimate",
        "ReviewIssue",
        "ReviewVerdict",
        "ReviewResult",
        "ReviewedAnswer",
        "HumanDecision",
        "ActionResult",
    )
    return JsonPlusSerializer(
        allowed_msgpack_modules=[
            *(("app.schemas.agents", name) for name in names),
            ("app.services.rag.types", "Citation"),
        ]
    )


def memory_checkpointer() -> InMemorySaver:
    """Development only; persistent adapters should use the same serializer."""
    return InMemorySaver(serde=checkpoint_serializer())
