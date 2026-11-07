"""Generated from packages/contracts/domain.json; do not edit."""

from typing import Literal

# fmt: off
ClaimStatus = Literal["draft", "gathering_evidence", "preparation_requested", "prepared", "filed_by_user", "insurer_decision_received", "resolved_without_filing", "submitted_in_claimwise"]
ManualClaimStatus = Literal["draft", "gathering_evidence", "filed_by_user", "insurer_decision_received", "resolved_without_filing"]
RepairStatus = Literal["unknown", "pending", "scheduled", "completed"]
InsurerOutcome = Literal["unknown", "approved", "partially_approved", "denied"]
RunStatus = Literal["running", "awaiting_information", "awaiting_review", "completed", "blocked", "rejected", "failed"]
UploadStatus = Literal["pending", "saved"]
IngestionStatus = Literal["not_started", "processing", "ready", "failed"]

CLAIM_STATUS_LABELS: dict[ClaimStatus, str] = {
  "draft": "Draft",
  "gathering_evidence": "Gathering evidence",
  "preparation_requested": "Preparation requested",
  "prepared": "Package prepared",
  "filed_by_user": "Filed by me with insurer",
  "insurer_decision_received": "Insurer decision received",
  "resolved_without_filing": "Resolved without filing",
  "submitted_in_claimwise": "Submitted in Jeeves"
}
