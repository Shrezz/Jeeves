import { Router, type IRouter } from "express";
import { getAuth } from "@clerk/express";
import { and, asc, desc, eq, inArray, isNull, sql } from "drizzle-orm";
import { db, claimsTable, claimMessagesTable, claimEvidenceTable, claimGuidanceTable, policiesTable } from "@workspace/db";
import {
  CreateClaimBody, CreateClaimResponse, GetClaimParams, GetClaimResponse,
  ListClaimsResponse, SaveClaimMessageBody, SaveClaimMessageParams, SaveClaimMessageResponse,
} from "@workspace/api-zod";
import { ClaimRequestError, ownedClaim, serializeClaim, serializeClaimPolicy, serializeEvidence, serializeMessage, serializeGuidance } from "../lib/claims";
import evidenceRouter from "./claim-evidence";
import guidanceRouter from "./claim-guidance";
import reviewRouter from "./claim-review";

const router: IRouter = Router();

router.use("/claims", (req, res, next) => {
  res.set("Cache-Control", "private, no-store");
  if (req.method !== "GET" && req.get("sec-fetch-site") === "cross-site") {
    res.status(403).json({ error: "Cross-site requests are not allowed." });
    return;
  }
  next();
});

router.get("/claims", async (req, res): Promise<void> => {
  const claims = await db.select().from(claimsTable).where(eq(claimsTable.ownerId, getAuth(req).userId!))
    .orderBy(desc(claimsTable.updatedAt), desc(claimsTable.id));
  res.json(ListClaimsResponse.parse(claims.map(serializeClaim)));
});

router.post("/claims", async (req, res): Promise<void> => {
  const body = CreateClaimBody.safeParse(req.body);
  if (!body.success || !body.data.title.trim()) {
    res.status(400).json({ error: "Enter a claim title of up to 160 characters." });
    return;
  }
  const ownerId = getAuth(req).userId!;
  if (body.data.policyId) {
    const [policy] = await db.select({ id: policiesTable.id }).from(policiesTable).where(and(
      eq(policiesTable.id, body.data.policyId), eq(policiesTable.ownerId, ownerId), eq(policiesTable.status, "saved"),
    ));
    if (!policy) throw new ClaimRequestError(404, "Policy not found.");
  }
  await db.insert(claimsTable).values({
    id: body.data.id, ownerId, title: body.data.title.trim(), policyId: body.data.policyId ?? null,
  }).onConflictDoNothing({ target: claimsTable.id });
  const claim = await ownedClaim(body.data.id, ownerId);
  if (claim.title !== body.data.title.trim() || claim.policyId !== (body.data.policyId ?? null)) {
    throw new ClaimRequestError(400, "This draft was already saved with different details. Open the saved draft or start a new one.");
  }
  res.status(201).json(CreateClaimResponse.parse(serializeClaim(claim)));
});

router.get("/claims/:id", async (req, res): Promise<void> => {
  const params = GetClaimParams.safeParse(req.params);
  if (!params.success) throw new ClaimRequestError(400, "Invalid claim ID.");
  const ownerId = getAuth(req).userId!;
  // A consistent snapshot prevents a message/expense update from splitting
  // the returned history and total across different committed versions.
  const workspace = await db.transaction(async (tx) => {
    const [claim] = await tx.select().from(claimsTable).where(and(
      eq(claimsTable.id, params.data.id), eq(claimsTable.ownerId, ownerId),
    )).for("share");
    if (!claim) throw new ClaimRequestError(404, "Claim not found.");
    const messages = await tx.select().from(claimMessagesTable).where(eq(claimMessagesTable.claimId, claim.id))
      .orderBy(asc(claimMessagesTable.createdAt), asc(claimMessagesTable.id));
    const evidence = await tx.select().from(claimEvidenceTable).where(and(
      eq(claimEvidenceTable.claimId, claim.id), eq(claimEvidenceTable.status, "saved"),
    )).orderBy(asc(claimEvidenceTable.createdAt));
    const [policy] = claim.policyId ? await tx.select().from(policiesTable).where(and(
      eq(policiesTable.id, claim.policyId), eq(policiesTable.ownerId, ownerId), eq(policiesTable.status, "saved"),
    )) : [];
    const guidance = await tx.select().from(claimGuidanceTable).where(eq(claimGuidanceTable.claimId, claim.id))
      .orderBy(asc(claimGuidanceTable.createdAt));
    return { claim: serializeClaim(claim), messages: messages.map((m) => serializeMessage(m, evidence)),
      evidence: evidence.map(serializeEvidence), guidance: guidance.map(serializeGuidance),
      policy: policy ? serializeClaimPolicy(policy) : null };
  });
  res.json(GetClaimResponse.parse(workspace));
});

router.post("/claims/:id/messages", async (req, res): Promise<void> => {
  const params = SaveClaimMessageParams.safeParse(req.params);
  const body = SaveClaimMessageBody.safeParse(req.body);
  if (!params.success || !body.success) throw new ClaimRequestError(400, "Enter a valid message, expense, and request type.");
  const input = body.data;
  const attachmentIds = [...new Set(input.attachmentIds ?? [])];
  const expense = input.expense == null ? null : input.expense.toFixed(2);
  const content = input.content.trim() || (input.kind === "preparation_request" ? "Preparation requested." : "");
  if (input.kind === "ask" && !content && expense === null && !attachmentIds.length) {
    throw new ClaimRequestError(400, "Enter a message, expense, or attach evidence before sending.");
  }
  if (input.kind === "status_update" && (!input.status || !content)) {
    throw new ClaimRequestError(400, "Choose a status and enter a comment.");
  }
  if (input.kind !== "status_update" && input.status) {
    throw new ClaimRequestError(400, "Use Update status to record a status.");
  }
  const result = await db.transaction(async (tx) => {
    const [claim] = await tx.select().from(claimsTable).where(and(
      eq(claimsTable.id, params.data.id), eq(claimsTable.ownerId, getAuth(req).userId!),
    )).for("update");
    if (!claim) throw new ClaimRequestError(404, "Claim not found.");
    const [previous] = await tx.select().from(claimMessagesTable).where(eq(claimMessagesTable.id, input.clientMessageId));
    if (previous) {
      if (previous.claimId !== claim.id) throw new ClaimRequestError(404, "Message not found.");
      const previousEvidence = await tx.select().from(claimEvidenceTable).where(eq(claimEvidenceTable.messageId, previous.id));
      if (previous.content !== content || previous.kind !== input.kind || previous.expense !== expense ||
          previous.status !== (input.status ?? null) ||
          JSON.stringify(previousEvidence.map((e) => e.id).sort()) !== JSON.stringify([...attachmentIds].sort())) {
        throw new ClaimRequestError(400, "This retry has different details. Check the saved conversation before sending again.");
      }
      return serializeMessage(previous, previousEvidence);
    }
    const evidence = attachmentIds.length ? await tx.select().from(claimEvidenceTable).where(and(
      inArray(claimEvidenceTable.id, attachmentIds), eq(claimEvidenceTable.claimId, claim.id),
      eq(claimEvidenceTable.status, "saved"), isNull(claimEvidenceTable.messageId),
    )) : [];
    if (evidence.length !== attachmentIds.length) throw new ClaimRequestError(400, "One or more attachments are unavailable or already attached to a message.");
    const [message] = await tx.insert(claimMessagesTable).values({
      id: input.clientMessageId, claimId: claim.id, content, kind: input.kind, expense,
      status: input.kind === "status_update" ? input.status : null,
      processingStatus: input.kind === "status_update" ? "recorded" : "saved_for_processing",
    }).returning();
    if (attachmentIds.length) await tx.update(claimEvidenceTable).set({ messageId: message.id })
      .where(and(eq(claimEvidenceTable.claimId, claim.id), inArray(claimEvidenceTable.id, attachmentIds)));
    await tx.update(claimsTable).set({
      ...(claim.title === "New claim" && input.kind === "ask" && content ? { title: content.replace(/\s+/g, " ").slice(0, 100) } : {}),
      latestUpdate: content || (expense !== null ? "Expense recorded." : "Evidence attached."),
      updatedAt: new Date(),
      ...(input.kind === "status_update" && input.status === "insurer_decision_received" ? { insurerOutcomeSource: "user_reported" as const } : {}),
      totalExpenses: sql`${claimsTable.totalExpenses} + ${expense ?? "0"}::numeric`,
      status: input.kind === "status_update" ? input.status!
        : input.kind === "preparation_request" ? "preparation_requested"
        : claim.status === "draft" ? "gathering_evidence" : claim.status,
    }).where(eq(claimsTable.id, claim.id));
    return serializeMessage(message, evidence.map((e) => ({ ...e, messageId: message.id })));
  });
  res.status(201).json(SaveClaimMessageResponse.parse(result));
});

router.use(evidenceRouter);
router.use(guidanceRouter);
router.use(reviewRouter);

router.use((error: unknown, req: import("express").Request, res: import("express").Response, next: import("express").NextFunction) => {
  if (res.headersSent) { next(error); return; }
  if (error instanceof ClaimRequestError) { res.status(error.status).json({ error: error.message }); return; }
  req.log.error({ errorType: error instanceof Error ? error.name : "Unknown" }, "Claim request failed");
  res.status(500).json({ error: "Your claim could not be saved or loaded. Please try again; your draft has not been cleared." });
});

export default router;
