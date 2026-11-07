// Generated from packages/contracts/domain.json; do not edit.

export const CLAIM_STATUS_VALUES = ["draft", "gathering_evidence", "preparation_requested", "prepared", "filed_by_user", "insurer_decision_received", "resolved_without_filing", "submitted_in_claimwise"] as const;
export type ClaimStatus = (typeof CLAIM_STATUS_VALUES)[number];
export const MANUAL_CLAIM_STATUS_VALUES = ["draft", "gathering_evidence", "filed_by_user", "insurer_decision_received", "resolved_without_filing"] as const;
export type ManualClaimStatus = (typeof MANUAL_CLAIM_STATUS_VALUES)[number];
export const REPAIR_STATUS_VALUES = ["unknown", "scheduled", "completed"] as const;
export type RepairStatus = (typeof REPAIR_STATUS_VALUES)[number];
export const INSURER_OUTCOME_VALUES = ["unknown", "approved", "partially_approved", "denied"] as const;
export type InsurerOutcome = (typeof INSURER_OUTCOME_VALUES)[number];
export const RUN_STATUS_VALUES = ["running", "awaiting_information", "awaiting_review", "completed", "blocked", "rejected", "failed"] as const;
export type RunStatus = (typeof RUN_STATUS_VALUES)[number];
export const UPLOAD_STATUS_VALUES = ["pending", "saved"] as const;
export type UploadStatus = (typeof UPLOAD_STATUS_VALUES)[number];
export const INGESTION_STATUS_VALUES = ["not_started", "processing", "ready", "failed"] as const;
export type IngestionStatus = (typeof INGESTION_STATUS_VALUES)[number];

export const CLAIM_STATUS_LABELS: Record<ClaimStatus, string> = {
  "draft": "Draft",
  "gathering_evidence": "Gathering evidence",
  "preparation_requested": "Preparation requested",
  "prepared": "Package prepared",
  "filed_by_user": "Filed by me with insurer",
  "insurer_decision_received": "Insurer decision received",
  "resolved_without_filing": "Resolved without filing",
  "submitted_in_claimwise": "Submitted in Claimwise"
};
