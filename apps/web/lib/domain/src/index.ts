export * from "./generated";
export * from "./prompt-scope";

import { CLAIM_STATUS_LABELS, CLAIM_STATUS_VALUES } from "./generated";
import type { ClaimStatus } from "./generated";

/** This checks identifier shape only. The caller must authenticate the Clerk session. */
export function clerkUserId(subject: string): string {
  if (subject !== subject.trim() || !/^user_[A-Za-z0-9_]+$/.test(subject)) {
    throw new Error("Expected an authenticated Clerk user ID");
  }
  return subject;
}

/** Keep historical message labels readable; new claim records use canonical codes. */
export function claimStatusLabel(status: string): string {
  return (CLAIM_STATUS_VALUES as readonly string[]).includes(status)
    ? CLAIM_STATUS_LABELS[status as ClaimStatus]
    : status;
}

// A local retrieval plus a reviewed model response may take several minutes on a cold start.
export const GUIDANCE_LEASE_MS = 6 * 60_000;
