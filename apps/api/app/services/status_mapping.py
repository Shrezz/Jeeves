"""Translate legacy status values without conflating repair, filing, and payment."""

from dataclasses import dataclass
from typing import get_args

from app.schemas.domain import CLAIM_STATUS_LABELS, ClaimStatus, InsurerOutcome, RepairStatus


@dataclass(frozen=True)
class StatusMapping:
    status: ClaimStatus | None = None
    repair_status: RepairStatus | None = None
    insurer_outcome: InsurerOutcome | None = None


def map_legacy_status(
    value: str, *, current_status: ClaimStatus | None = None, without_filing_confirmed: bool = False
) -> StatusMapping:
    """Migration/adapter helper, not authorization to apply a status or claim submission."""
    labels = {label: code for code, label in CLAIM_STATUS_LABELS.items()}
    if value in labels:
        return StatusMapping(status=labels[value])
    if value in get_args(ClaimStatus):
        return StatusMapping(status=value)
    if value == "open":
        return StatusMapping(status=current_status or "draft")
    if value in {"repair_scheduled", "repaired"}:
        return StatusMapping(
            repair_status="scheduled" if value == "repair_scheduled" else "completed"
        )
    if value == "user_reported_submitted":
        return StatusMapping(status="filed_by_user")
    if value in {"user_reported_approved", "user_reported_denied"}:
        return StatusMapping(
            status="insurer_decision_received",
            insurer_outcome="approved" if value == "user_reported_approved" else "denied",
        )
    if value == "resolved" and without_filing_confirmed:
        return StatusMapping(status="resolved_without_filing")
    raise ValueError(
        "Legacy status needs explicit reconciliation; do not infer filing or resolution"
    )
