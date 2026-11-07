import { and, asc, eq } from "drizzle-orm";
import {
  db, claimReviewsTable, claimMessagesTable, claimEvidenceTable, claimGuidanceTable, policiesTable,
  type StoredClaim,
} from "@workspace/db";
import { GetClaimReviewResponse } from "@workspace/api-zod";
import { serializeClaim, serializeClaimPolicy, serializeEvidence, serializeGuidance, serializeMessage } from "./claims";

export type ReviewTransaction = Parameters<Parameters<typeof db.transaction>[0]>[0];

export async function loadClaimReview(tx: ReviewTransaction, claim: StoredClaim) {
  const [review] = await tx.select().from(claimReviewsTable).where(eq(claimReviewsTable.claimId, claim.id));
  // Submitted reviews are an immutable record of exactly what was submitted.
  if (review?.submittedAt && review.snapshot) return GetClaimReviewResponse.parse(review.snapshot);
  const messages = await tx.select().from(claimMessagesTable).where(eq(claimMessagesTable.claimId, claim.id))
    .orderBy(asc(claimMessagesTable.createdAt), asc(claimMessagesTable.id));
  const evidence = await tx.select().from(claimEvidenceTable).where(and(
    eq(claimEvidenceTable.claimId, claim.id), eq(claimEvidenceTable.status, "saved"),
  )).orderBy(asc(claimEvidenceTable.createdAt));
  const guidance = await tx.select().from(claimGuidanceTable).where(eq(claimGuidanceTable.claimId, claim.id));
  const [policy] = claim.policyId ? await tx.select().from(policiesTable).where(and(
    eq(policiesTable.id, claim.policyId), eq(policiesTable.ownerId, claim.ownerId), eq(policiesTable.status, "saved"),
  )) : [];
  const incidentSummary = messages.filter((m) => m.kind === "ask" && m.content.trim())
    .map((m) => ({ id: m.id, content: m.content, createdAt: m.createdAt.toISOString() }));
  const expenses = messages.filter((m) => m.expense !== null)
    .map((m) => ({ id: m.id, content: m.content, expense: Number(m.expense), createdAt: m.createdAt.toISOString() }));
  const missingFields = [
    ...(!incidentSummary.length ? ["Incident description has not been provided."] : []),
    ...(!policy ? ["No saved policy is linked to this claim."] : []),
    ...(!evidence.length ? ["No supporting documents, photos, or videos are saved."] : []),
  ];
  return GetClaimReviewResponse.parse({
    workspace: {
      claim: serializeClaim(claim), policy: policy ? serializeClaimPolicy(policy) : null,
      messages: messages.map((m) => serializeMessage(m, evidence)), evidence: evidence.map(serializeEvidence),
      guidance: guidance.map(serializeGuidance),
    },
    incidentSummary, expenses, citedClauses: [],
    reviewerResult: "Saved records loaded successfully. This is a basic completeness check, not a coverage assessment or an insurer review. Policy wording has not been analyzed.",
    missingFields, comments: review?.comments ?? "", version: review?.version ?? 0,
    sourceUpdatedAt: claim.updatedAt.toISOString(), submittedAt: null,
  });
}
