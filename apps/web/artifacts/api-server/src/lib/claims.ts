import { and, eq } from "drizzle-orm";
import { db, claimsTable, type StoredClaim, type StoredClaimEvidence, type StoredClaimMessage, type StoredClaimGuidance } from "@workspace/db";

export { ClaimRequestError } from "./claim-errors";
import { ClaimRequestError } from "./claim-errors";

export async function ownedClaim(id: string, ownerId: string) {
  const [claim] = await db.select().from(claimsTable).where(and(eq(claimsTable.id, id), eq(claimsTable.ownerId, ownerId)));
  if (!claim) throw new ClaimRequestError(404, "Claim not found.");
  return claim;
}

export function serializeClaim(c: StoredClaim) {
  return { id: c.id, title: c.title, policyId: c.policyId, status: c.status, totalExpenses: Number(c.totalExpenses),
    latestUpdate: c.latestUpdate, createdAt: c.createdAt.toISOString(), updatedAt: c.updatedAt.toISOString() };
}

export function serializeMessage(m: StoredClaimMessage, evidence: StoredClaimEvidence[]) {
  return { id: m.id, claimId: m.claimId, content: m.content, kind: m.kind, expense: m.expense === null ? null : Number(m.expense),
    status: m.status, processingStatus: m.processingStatus, createdAt: m.createdAt.toISOString(),
    attachmentIds: evidence.filter((e) => e.messageId === m.id).map((e) => e.id) };
}

export function serializeEvidence(e: StoredClaimEvidence) {
  return { id: e.id, claimId: e.claimId, messageId: e.messageId, fileName: e.fileName, size: e.size,
    contentType: e.contentType, createdAt: e.createdAt.toISOString(),
    documentUrl: `/api/claims/${e.claimId}/evidence/${e.id}/document` };
}

export function serializeGuidance(g: StoredClaimGuidance) {
  return { id: g.id, claimId: g.claimId, messageId: g.messageId, content: g.content, sources: g.sources, ...(g.workflow ? {workflow:g.workflow} : {}), state: g.state,
    createdAt: g.createdAt.toISOString(), updatedAt: g.updatedAt.toISOString() };
}

export { serializePolicy as serializeClaimPolicy } from "./serialize-policy";
