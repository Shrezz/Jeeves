"""Validated values passed between the agents; these are not HTTP request schemas."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.domain import ClaimStatus, InsurerOutcome, ManualClaimStatus, RepairStatus

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Money = Annotated[Decimal, Field(ge=0, allow_inf_nan=False, decimal_places=2)]
Route = Literal["answer_claim", "save_claim_status", "file_claim"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AgentRequest(Contract):
    message: Text
    claim_id: Text | None = None
    explicit_route: Route | None = None
    web_search_query: Text | None = Field(default=None, max_length=500)


class RouteDecision(Contract):
    route: Route | None
    clarification: Text | None = None

    @model_validator(mode="after")
    def require_route_or_question(self) -> Self:
        if (self.route is None) == (self.clarification is None):
            raise ValueError("Provide either a route or a clarification question")
        return self


class IncidentFacts(Contract):
    description: Text | None = None
    cause: Text | None = None
    occurred_on: date | None = None
    repair_cost: Money | None = None
    repair_status: RepairStatus | None = None


class ClaimSnapshot(Contract):
    claim_id: Text
    user_id: Text
    policy_id: Text
    policy_version: Text
    version: int = Field(ge=1)
    facts: IncidentFacts
    status: ClaimStatus = "draft"
    insurer_outcome: InsurerOutcome = "unknown"
    insurer_outcome_source: Literal["user_reported"] | None = None
    notes: list[Text] = Field(default_factory=list)
    attachment_ids: list[Text] = Field(default_factory=list)


class CoverageDraft(Contract):
    conclusion: Literal["likely_covered", "likely_not_covered", "unclear"]
    explanation: Text
    citation_ids: list[Text] = Field(default_factory=list)
    missing_information: list[Text] = Field(default_factory=list)
    # These are proposed inputs, checked against the facts/policy by the reviewer.
    # A missing value means unknown, never an assumed zero.
    covered_amount: Money | None = None
    deductible: Money | None = None


class StatusDraft(Contract):
    note: Text
    status: ManualClaimStatus | None = None
    insurer_outcome: InsurerOutcome | None = None
    facts: IncidentFacts = Field(default_factory=IncidentFacts)
    missing_information: list[Text] = Field(default_factory=list)

    @model_validator(mode="after")
    def outcome_requires_reported_decision(self) -> Self:
        if self.insurer_outcome is not None and self.status != "insurer_decision_received":
            raise ValueError("An insurer outcome requires a user-reported decision status")
        return self


class PacketDraft(Contract):
    narrative: Text
    facts: IncidentFacts
    coverage: CoverageDraft
    attachment_ids: list[Text] = Field(default_factory=list)
    missing_information: list[Text] = Field(default_factory=list)


class PaymentEstimate(Contract):
    covered_amount: Money
    deductible: Money
    estimated_payment: Money
    basis: str = "Simplified demo estimate: covered amount minus a flat deductible, minimum zero."


class ReviewIssue(Contract):
    check: Text
    detail: Text
    field: Text | None = None
    citation_ids: list[Text] = Field(default_factory=list)


class ReviewVerdict(Contract):
    outcome: Literal["pass", "revise", "needs_information"]
    issues: list[ReviewIssue] = Field(default_factory=list)
    questions: list[Text] = Field(default_factory=list)
    evidence_query: Text | None = None

    @model_validator(mode="after")
    def require_actionable_feedback(self) -> Self:
        if self.outcome == "pass" and (self.issues or self.questions):
            raise ValueError("A passed review cannot contain unresolved issues or questions")
        if self.outcome == "revise" and not self.issues:
            raise ValueError("A revision needs specific issues")
        if self.outcome == "needs_information" and not self.questions:
            raise ValueError("Missing information needs specific questions")
        if self.evidence_query and self.outcome != "needs_information":
            raise ValueError("An evidence search must explain what information is missing")
        return self


class ReviewResult(Contract):
    route: Route
    artifact_version: int = Field(ge=1)
    verdict: ReviewVerdict


class ReviewedAnswer(Contract):
    coverage: CoverageDraft
    estimate: PaymentEstimate | None = None
    next_actions: list[Literal["save_resolution", "prepare_packet"]] = Field(default_factory=list)


class HumanDecision(Contract):
    artifact_version: int = Field(ge=1)
    action: Literal["approve", "edit", "reject"]
    feedback: Text | None = None

    @model_validator(mode="after")
    def require_edit_feedback(self) -> Self:
        if self.action == "edit" and self.feedback is None:
            raise ValueError("Describe the requested edits in feedback")
        return self


class ClaimTemplate(Contract):
    name: Text = "Synthetic homeowners claim packet"
    required_facts: tuple[Literal["description", "cause", "occurred_on", "repair_cost"], ...] = (
        "description",
        "cause",
        "occurred_on",
        "repair_cost",
    )


class EvidencePlan(Contract):
    reuse: bool
    query: Text | None = None

    @model_validator(mode="after")
    def require_query(self) -> Self:
        if not self.reuse and not self.query:
            raise ValueError("A new search requires a query")
        return self


class Clarification(Contract):
    message: Text
    claim_id: Text | None = None


class ActionResult(Contract):
    outcome: Literal["saved", "prepared"]
    claim_id: Text
    claim_version: int = Field(ge=1)
    artifact_id: Text | None = None
    mode: Literal["fixture", "integrated"]
