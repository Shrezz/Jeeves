"""Public API contracts expose reviewed results and narrowly scoped human actions."""

from typing import Literal

from pydantic import Field, model_validator

from app.schemas.agents import (
    ActionResult,
    Clarification,
    Contract,
    HumanDecision,
    PacketDraft,
    PaymentEstimate,
    ReviewedAnswer,
    ReviewIssue,
    Route,
    StatusDraft,
    Text,
)
from app.services.rag.types import Citation


class StartRun(Contract):
    request_key: Text = Field(max_length=100)
    policy_id: Text
    claim_id: Text | None = None
    message: Text = Field(max_length=12000)
    explicit_route: Route | None = None


class ResumeRun(Contract):
    request_key: Text = Field(max_length=100)
    interrupt_id: Text
    clarification: Clarification | None = None
    decision: HumanDecision | None = None

    @model_validator(mode="after")
    def exactly_one_response(self):
        if (self.clarification is None) == (self.decision is None):
            raise ValueError("Provide either clarification or decision")
        return self


class PendingAction(Contract):
    interrupt_id: str
    kind: Literal["clarification", "human_review"]
    route: Route | None = None
    questions: list[str] = Field(default_factory=list)
    artifact_version: int | None = None
    draft: StatusDraft | PacketDraft | None = None
    estimate: PaymentEstimate | None = None
    actions: list[Literal["approve", "edit", "reject"]] = Field(default_factory=list)


class RunView(Contract):
    run_id: str
    mode: Literal["fixture", "integrated"]
    model_mode: Literal["fixture", "nebius", "injected"] = "injected"
    status: Literal[
        "running",
        "awaiting_information",
        "awaiting_review",
        "completed",
        "blocked",
        "rejected",
        "failed",
    ]
    route: Route | None = None
    stages: list[str] = Field(default_factory=list)
    answer: ReviewedAnswer | None = None
    action_result: ActionResult | None = None
    citations: list[Citation] = Field(default_factory=list)
    pending: PendingAction | None = None
    issues: list[ReviewIssue] = Field(default_factory=list)
    error: str | None = None
