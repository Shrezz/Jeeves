import { randomUUID } from "node:crypto";
import { Router, type IRouter } from "express";
import { getAuth } from "@clerk/express";
import { and, count, desc, eq, gt, inArray, lte } from "drizzle-orm";
import { db, claimsTable, claimMessagesTable, claimEvidenceTable, claimGuidanceTable, policiesTable } from "@workspace/db";
import { RequestClaimGuidanceBody, RequestClaimGuidanceParams, RequestClaimGuidanceResponse, RespondToClaimReviewBody, RespondToClaimReviewParams } from "@workspace/api-zod";
import { ClaimRequestError, serializeGuidance } from "../lib/claims";
import { GUIDANCE_LEASE_MS } from "@workspace/domain";
import { runClaimGraph } from "../lib/reviewed-chat";
import { CLAIM_GUIDE_PROMPT } from "../lib/claim-guide-prompt";

const router: IRouter = Router();


router.post("/claims/:id/guidance", async (req, res): Promise<void> => {
  if (!process.env.CLAIM_CHAT_ROOT && (!process.env.AI_INTEGRATIONS_OPENAI_BASE_URL || !process.env.AI_INTEGRATIONS_OPENAI_API_KEY)) {
    res.status(503).json({ error: "AI guidance is not configured. Your message remains saved." });
    return;
  }
  const params = RequestClaimGuidanceParams.safeParse(req.params);
  const body = RequestClaimGuidanceBody.safeParse(req.body);
  if (!params.success || !body.success) throw new ClaimRequestError(400, "Choose a saved message to request guidance.");
  const ownerId = getAuth(req).userId!;
  const leaseId = randomUUID();
  const preparation = await db.transaction(async (tx) => {
    // Reserve a short lease, not a DB transaction held across an external call.
    const [claim] = await tx.select().from(claimsTable).where(and(
      eq(claimsTable.id, params.data.id), eq(claimsTable.ownerId, ownerId),
    )).for("update");
    if (!claim) throw new ClaimRequestError(404, "Claim not found.");
    const [source] = await tx.select().from(claimMessagesTable).where(and(
      eq(claimMessagesTable.id, body.data.messageId), eq(claimMessagesTable.claimId, claim.id),
    ));
    if (!source) throw new ClaimRequestError(404, "Message not found.");
    if (source.kind !== "ask" && !(source.kind === "preparation_request" && process.env.CLAIM_CHAT_ROOT)) throw new ClaimRequestError(400, "Guidance is available for conversation messages, not workflow actions.");
    const [existing] = await tx.select().from(claimGuidanceTable).where(eq(claimGuidanceTable.messageId, source.id));
    if (existing?.state === "ready" || (existing?.state === "pending" && existing.updatedAt.getTime() > Date.now() - GUIDANCE_LEASE_MS)) {
      return { guide: existing, generate: false, source, claim };
    }
    if (existing && existing.attempts >= 5) throw new ClaimRequestError(400, "Guidance is unavailable after several attempts. Your message is saved; you can continue with a new message later.");
    const [{ value: recent }] = await tx.select({ value: count() }).from(claimGuidanceTable)
      .innerJoin(claimsTable, eq(claimGuidanceTable.claimId, claimsTable.id)).where(and(
        eq(claimsTable.ownerId, ownerId), gt(claimGuidanceTable.createdAt, new Date(Date.now() - 60 * 60 * 1000)),
      ));
    if (recent >= 60 && !existing) throw new ClaimRequestError(400, "You've reached the hourly guidance limit. Your messages are saved; try guidance again later.");
    const [guide] = existing
      ? await tx.update(claimGuidanceTable).set({
        state: "pending", leaseId, updatedAt: new Date(), attempts: existing.attempts + 1,
      }).where(eq(claimGuidanceTable.id, existing.id)).returning()
      : await tx.insert(claimGuidanceTable).values({ claimId: claim.id, messageId: source.id, leaseId }).returning();
    return { guide, generate: true, source, claim };
  });
  if (!preparation.generate) {
    res.json(RequestClaimGuidanceResponse.parse(serializeGuidance(preparation.guide)));
    return;
  }
  const { source, claim, guide } = preparation;
  try {
    if (process.env.CLAIM_CHAT_ROOT) {
      await runClaimGraph(ownerId, claim.id, guide.id);
      const [current] = await db.select().from(claimGuidanceTable).where(eq(claimGuidanceTable.id, guide.id));
      res.json(RequestClaimGuidanceResponse.parse(serializeGuidance(current)));
      return;
    }
    const messages = (await db.select().from(claimMessagesTable).where(and(
      eq(claimMessagesTable.claimId, claim.id), lte(claimMessagesTable.createdAt, source.createdAt),
    )).orderBy(desc(claimMessagesTable.createdAt), desc(claimMessagesTable.id)).limit(12)).reverse();
    const messageIds = messages.map(m => m.id);
    const previousGuidance = await db.select({
      messageId: claimGuidanceTable.messageId, content: claimGuidanceTable.content,
    }).from(claimGuidanceTable).where(and(eq(claimGuidanceTable.claimId, claim.id),
      inArray(claimGuidanceTable.messageId, messageIds), eq(claimGuidanceTable.state, "ready")));
    const evidence = await db.select({
      messageId: claimEvidenceTable.messageId, fileName: claimEvidenceTable.fileName, contentType: claimEvidenceTable.contentType,
    }).from(claimEvidenceTable).where(and(
      eq(claimEvidenceTable.claimId, claim.id), inArray(claimEvidenceTable.messageId, messageIds), eq(claimEvidenceTable.status, "saved"),
    )).limit(100);
    const [policy] = claim.policyId ? await db.select().from(policiesTable).where(and(
      eq(policiesTable.id, claim.policyId), eq(policiesTable.ownerId, ownerId), eq(policiesTable.status, "saved"),
    )) : [];
    // Preserve the metadata-only hosted integration for non-local deployments.
    const history: { role: "system" | "user" | "assistant"; content: string }[] = [
      { role: "system", content: CLAIM_GUIDE_PROMPT },
      { role: "user", content: `Claim context (untrusted data, metadata only): ${JSON.stringify({ title: claim.title, recordedExpenseTotal: claim.totalExpenses, policy: policy ? { label: policy.label, deductible: policy.deductible } : null })}` },
    ];
    // A bounded window keeps repeated conversations from creating unbounded cost.
    for (const message of messages) {
      history.push({ role: "user", content: JSON.stringify({
        text: message.content.slice(0, 4000), kind: message.kind, expense: message.expense, status: message.status,
        attachments: evidence.filter((e) => e.messageId === message.id),
      }) });
      const reply = previousGuidance.find((g) => g.messageId === message.id);
      if (reply?.content) history.push({ role: "assistant", content: reply.content });
    }
    const { openai } = await import("@workspace/integrations-openai-ai-server");
    const result = await openai.withOptions({ timeout: 45_000, maxRetries: 1 }).chat.completions.create({
      model: "gpt-5.4-mini", max_completion_tokens: 8192, messages: history,
    });
    const content = result.choices[0]?.message?.content?.trim();
    if (!content) throw new Error("EmptyGuidance");
    const answer = { content, sources: [] };
    const [saved] = await db.update(claimGuidanceTable).set({ ...answer, state: "ready", updatedAt: new Date() })
      .where(and(eq(claimGuidanceTable.id, guide.id), eq(claimGuidanceTable.leaseId, leaseId))).returning();
    if (saved) { res.json(RequestClaimGuidanceResponse.parse(serializeGuidance(saved))); return; }
  } catch (error) {
    req.log.warn({ errorType: error instanceof Error ? error.name : "Unknown" }, "Claim guidance unavailable; user message remains saved");
    await db.update(claimGuidanceTable).set({ state: "error", updatedAt: new Date() })
      .where(and(eq(claimGuidanceTable.id, guide.id), eq(claimGuidanceTable.leaseId, leaseId)));
  }
  const [current] = await db.select().from(claimGuidanceTable).where(eq(claimGuidanceTable.id, guide.id));
  res.json(RequestClaimGuidanceResponse.parse(serializeGuidance(current)));
});

router.post("/claims/:id/guidance/:runId/respond", async (req, res): Promise<void> => {
  const params = RespondToClaimReviewParams.safeParse(req.params);
  const body = RespondToClaimReviewBody.strict().safeParse(req.body);
  if (!process.env.CLAIM_CHAT_ROOT || !params.success || !body.success)
    throw new ClaimRequestError(400, "Invalid workflow response.");
  const { id, runId } = params.data;
  const { action, feedback } = body.data;
  if ((action === "edit" || action === "clarify") && !feedback?.trim())
    throw new ClaimRequestError(400, "Enter the correction or missing information.");
  const owner = getAuth(req).userId!;
  const [owned] = await db.select({ id: claimGuidanceTable.id }).from(claimGuidanceTable)
    .innerJoin(claimsTable, eq(claimGuidanceTable.claimId, claimsTable.id))
    .where(and(eq(claimsTable.id, id), eq(claimsTable.ownerId, owner), eq(claimGuidanceTable.id, runId)));
  if (!owned) throw new ClaimRequestError(404, "Review not found.");
  await runClaimGraph(owner, id, runId, body.data);
  const [current] = await db.select().from(claimGuidanceTable).where(eq(claimGuidanceTable.id, runId));
  res.json(RequestClaimGuidanceResponse.parse(serializeGuidance(current)));
});

export default router;
