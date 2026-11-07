import { randomUUID } from "node:crypto";
import { Router, type IRouter } from "express";
import { getAuth } from "@clerk/express";
import { and, eq, gt } from "drizzle-orm";
import { db, claimsTable, claimReviewsTable, claimMessagesTable, claimEvidenceTable } from "@workspace/db";
import {
  GetClaimReviewParams, GetClaimReviewResponse, SaveClaimReviewCommentsBody, SaveClaimReviewCommentsParams,
  SaveClaimReviewCommentsResponse, SubmitClaimReviewBody, SubmitClaimReviewParams, SubmitClaimReviewResponse,
} from "@workspace/api-zod";
import { ClaimRequestError } from "../lib/claims";
import { loadClaimReview, type ReviewTransaction } from "../lib/claim-review";

const router: IRouter = Router();
async function lockOwnedClaim(tx: ReviewTransaction, id: string, ownerId: string) {
  const [claim] = await tx.select().from(claimsTable).where(and(eq(claimsTable.id, id), eq(claimsTable.ownerId, ownerId))).for("update");
  if (!claim) throw new ClaimRequestError(404, "Claim not found.");
  return claim;
}
async function ensureReview(tx: ReviewTransaction, claimId: string) {
  await tx.insert(claimReviewsTable).values({ claimId }).onConflictDoNothing();
  const [review] = await tx.select().from(claimReviewsTable).where(eq(claimReviewsTable.claimId, claimId));
  return review;
}

router.get("/claims/:id/review", async (req, res) => {
  const params = GetClaimReviewParams.safeParse(req.params);
  if (!params.success) throw new ClaimRequestError(400, "Choose a valid claim.");
  const result = await db.transaction(async (tx) => {
    const [claim] = await tx.select().from(claimsTable).where(and(
      eq(claimsTable.id, params.data.id), eq(claimsTable.ownerId, getAuth(req).userId!),
    )).for("share");
    if (!claim) throw new ClaimRequestError(404, "Claim not found.");
    return loadClaimReview(tx, claim);
  });
  res.json(GetClaimReviewResponse.parse(result));
});

router.put("/claims/:id/review/comments", async (req, res) => {
  const params = SaveClaimReviewCommentsParams.safeParse(req.params);
  const body = SaveClaimReviewCommentsBody.safeParse(req.body);
  if (!params.success || !body.success) throw new ClaimRequestError(400, "Enter comments of up to 12,000 characters.");
  const result = await db.transaction(async (tx) => {
    const claim = await lockOwnedClaim(tx, params.data.id, getAuth(req).userId!);
    const review = await ensureReview(tx, claim.id);
    if (review.submittedAt) throw new ClaimRequestError(400, "This submitted review is read-only.");
    if (review.version !== body.data.version && review.comments !== body.data.comments) {
      throw new ClaimRequestError(400, "Comments changed in another session. Reload the review before saving; your text is kept here.");
    }
    if (review.comments !== body.data.comments) {
      await tx.update(claimReviewsTable).set({ comments: body.data.comments, version: review.version + 1, updatedAt: new Date() })
        .where(eq(claimReviewsTable.claimId, claim.id));
    }
    return loadClaimReview(tx, claim);
  });
  res.json(SaveClaimReviewCommentsResponse.parse(result));
});

router.post("/claims/:id/submit", async (req, res) => {
  const params = SubmitClaimReviewParams.safeParse(req.params);
  const body = SubmitClaimReviewBody.safeParse(req.body);
  if (!params.success || !body.success) throw new ClaimRequestError(400, "Load the review successfully before submitting.");
  const result = await db.transaction(async (tx) => {
    const claim = await lockOwnedClaim(tx, params.data.id, getAuth(req).userId!);
    const review = await ensureReview(tx, claim.id);
    // A replay of a successful submission returns its receipt, never a second event.
    if (review.submittedAt) return loadClaimReview(tx, claim);
    if (review.version !== body.data.version || claim.updatedAt.getTime() !== body.data.sourceUpdatedAt.getTime()) {
      throw new ClaimRequestError(400, "Claim details or comments changed. Reload the review and check them before submitting. Your comments are kept here.");
    }
    const [pendingUpload] = await tx.select({ id: claimEvidenceTable.id }).from(claimEvidenceTable).where(and(
      eq(claimEvidenceTable.claimId, claim.id), eq(claimEvidenceTable.status, "pending"),
      gt(claimEvidenceTable.createdAt, new Date(Date.now() - 15 * 60 * 1000)),
    )).limit(1);
    if (pendingUpload) throw new ClaimRequestError(400, "An evidence upload is still pending. Complete it before submitting.");
    await tx.update(claimReviewsTable).set({ comments: body.data.comments, version: review.version + 1, updatedAt: new Date() })
      .where(eq(claimReviewsTable.claimId, claim.id));
    const snapshot = await loadClaimReview(tx, claim);
    const submittedAt = new Date();
    const status = claim.status === "filed_by_user" || claim.status === "insurer_decision_received"
      ? claim.status : "submitted_in_claimwise";
    const notice = "Submitted in Claimwise. Not sent to an insurer.";
    const [updatedClaim] = await tx.update(claimsTable).set({ status, latestUpdate: notice, updatedAt: submittedAt })
      .where(eq(claimsTable.id, claim.id)).returning();
    await tx.insert(claimMessagesTable).values({
      id: randomUUID(), claimId: claim.id, kind: "status_update", content: notice,
      status: "submitted_in_claimwise", processingStatus: "recorded",
    });
    const submitted = SubmitClaimReviewResponse.parse({
      ...snapshot, submittedAt: submittedAt.toISOString(),
      workspace: { ...snapshot.workspace, claim: { ...snapshot.workspace.claim,
        status: updatedClaim.status, latestUpdate: notice, updatedAt: submittedAt.toISOString() } },
    });
    await tx.update(claimReviewsTable).set({ submittedAt, snapshot: submitted, updatedAt: submittedAt })
      .where(eq(claimReviewsTable.claimId, claim.id));
    return submitted;
  });
  res.json(SubmitClaimReviewResponse.parse(result));
});

export default router;
