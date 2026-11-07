"""Only serializable workflow data belongs in state; clients belong in runtime context."""

from typing import Literal, Required, TypedDict

from app.schemas.agents import (
    ActionResult,
    AgentRequest,
    ClaimSnapshot,
    CoverageDraft,
    HumanDecision,
    PacketDraft,
    PaymentEstimate,
    ReviewedAnswer,
    ReviewResult,
    RouteDecision,
    StatusDraft,
)
from app.services.rag.types import Citation

Draft = CoverageDraft | StatusDraft | PacketDraft


class AgentState(TypedDict, total=False):
    request: Required[AgentRequest]
    recent_turns: list[dict]
    chat_reply: dict
    scope_decision: Literal["allowed", "out_of_scope"]
    clarified_repair_status: Literal["pending", "scheduled", "completed"] | None
    run_id: str
    route: RouteDecision
    claim: ClaimSnapshot | None
    evidence: list[Citation]
    web_search: dict | None
    draft: Draft | None
    estimate: PaymentEstimate | None
    artifact_version: int
    review: ReviewResult | None
    answer: ReviewedAnswer | None
    questions: list[str]
    human_decision: HumanDecision | None
    latest_correction: str
    revision_count: int
    action_result: ActionResult | None
    phase: Literal[
        "routed",
        "needs_information",
        "review_pending",
        "revision_required",
        "human_review",
        "answer_ready",
        "approved",
        "rejected",
        "blocked",
        "completed",
    ]
