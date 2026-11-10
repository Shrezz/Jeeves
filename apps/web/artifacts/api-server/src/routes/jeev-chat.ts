import { randomUUID } from "node:crypto";
import { Router, type IRouter, type ErrorRequestHandler } from "express";
import { getAuth } from "@clerk/express";
import { and, asc, count, desc, eq, gt, isNull, sql } from "drizzle-orm";
import {
  db, policiesTable, jeevConversationsTable as conversations, jeevMessagesTable as messages,
  type StoredJeevConversation, type StoredJeevMessage,
} from "@workspace/db";
import {
  GetJeevConversationParams, GetJeevConversationResponse, ListJeevConversationsResponse,
  SendJeevMessageBody, SendJeevMessageParams, SendJeevMessageResponse,
} from "@workspace/api-zod";
import { ClaimRequestError } from "../lib/claims";
import { OUT_OF_SCOPE_MESSAGE, includePromptInHistory, promptInScope } from "@workspace/domain";
import { GUIDANCE_LEASE_MS as LEASE_MS } from "@workspace/domain";
import { isLocalPolicy } from "../lib/local-policy-index";
import { dashboardReply } from "../lib/dashboard-chat";

const router: IRouter = Router();
function conversationJson(row: StoredJeevConversation) {
  return { id: row.id, title: row.title, updatedAt: row.updatedAt.toISOString() };
}
function messageJson(row: StoredJeevMessage) {
  return {
    id: row.id, content: row.content, policyId: row.policyId, sources: row.sources, route: row.route ?? undefined, reply: row.reply, replyState: row.replyState,
    createdAt: row.createdAt.toISOString(), updatedAt: row.updatedAt.toISOString(),
  };
}

router.use((req, res, next) => {
  if (req.method !== "GET" && req.get("sec-fetch-site") === "cross-site") {
    res.status(403).json({ error: "Cross-site requests are not allowed." });
    return;
  }
  next();
});

router.get("/jeev/conversations", async (req, res) => {
  const rows = await db.select().from(conversations)
    .where(eq(conversations.ownerId, getAuth(req).userId!)).orderBy(desc(conversations.updatedAt));
  res.json(ListJeevConversationsResponse.parse(rows.map(conversationJson)));
});

router.get("/jeev/conversations/:id", async (req, res) => {
  const params = GetJeevConversationParams.safeParse(req.params);
  if (!params.success) throw new ClaimRequestError(400, "Choose a valid conversation.");
  const [conversation] = await db.select().from(conversations).where(and(
    eq(conversations.id, params.data.id), eq(conversations.ownerId, getAuth(req).userId!),
  ));
  if (!conversation) throw new ClaimRequestError(404, "Conversation not found.");
  const history = await db.select().from(messages).where(eq(messages.conversationId, conversation.id))
    .orderBy(asc(messages.createdAt), asc(messages.id));
  res.json(GetJeevConversationResponse.parse({ conversation: conversationJson(conversation), messages: history.map(messageJson) }));
});

router.post("/jeev/conversations/:id/messages", async (req, res) => {
  const params = SendJeevMessageParams.safeParse(req.params);
  const body = SendJeevMessageBody.safeParse(req.body);
  if (!params.success || !body.success || !body.data.content.trim()) {
    throw new ClaimRequestError(400, "Write a message before sending.");
  }
  const ownerId = getAuth(req).userId!;
  const content = body.data.content.trim();
  const policyId = body.data.policyId ?? null;
  const leaseId = randomUUID();
  const prepared = await db.transaction(async (tx) => {
    if (policyId) {
      const [policy] = await tx.select().from(policiesTable).where(and(
        eq(policiesTable.id, policyId), eq(policiesTable.ownerId, ownerId), eq(policiesTable.status, "saved"),
      ));
      if (!policy) throw new ClaimRequestError(404, "Policy not found.");
      if (!process.env.LOCAL_RAG_ROOT || !isLocalPolicy(policy) || policy.ingestionStatus !== "ready") {
        throw new ClaimRequestError(409, "That policy is not ready to search.");
      }
    }
    // Opening a chat makes no database record. Its first message starts a conversation,
    // in separate tables with no link to claims.
    await tx.insert(conversations).values({ id: params.data.id, ownerId, title: content.slice(0, 100) }).onConflictDoNothing();
    const [conversation] = await tx.select().from(conversations).where(and(
      eq(conversations.id, params.data.id), eq(conversations.ownerId, ownerId),
    )).for("update");
    if (!conversation) throw new ClaimRequestError(404, "Conversation not found.");
    const [existing] = await tx.select().from(messages).where(eq(messages.id, body.data.messageId));
    if (existing && (existing.conversationId !== conversation.id || existing.content !== content || existing.policyId !== policyId)) {
      throw new ClaimRequestError(400, "This message reference cannot be reused for different content.");
    }
    if (existing?.replyState === "ready" || (existing?.replyState === "pending" && existing.updatedAt.getTime() > Date.now() - LEASE_MS)) {
      return { row: existing, generate: false };
    }
    const [pending] = await tx.select().from(messages).where(and(
      eq(messages.conversationId, conversation.id), eq(messages.replyState, "pending"),
      gt(messages.updatedAt, new Date(Date.now() - LEASE_MS)),
    )).limit(1);
    if (pending) throw new ClaimRequestError(400, "Please wait for Jeeves to finish replying.");
    if (existing && existing.attempts >= 5) throw new ClaimRequestError(400, "Reply retries are exhausted. Your message is saved; try a new message later.");
    const [{ value: recent }] = await tx.select({ value: count() }).from(messages)
      .innerJoin(conversations, eq(conversations.id, messages.conversationId)).where(and(
        eq(conversations.ownerId, ownerId), gt(messages.createdAt, new Date(Date.now() - 3_600_000)),
      ));
    if (!existing && recent >= 60) throw new ClaimRequestError(400, "You've reached the hourly chat limit. Please try again later.");
    const [row] = existing
      ? await tx.update(messages).set({ replyState: "pending", leaseId, attempts: existing.attempts + 1, updatedAt: new Date() })
        .where(eq(messages.id, existing.id)).returning()
      : await tx.insert(messages).values({ id: body.data.messageId, conversationId: conversation.id, content, policyId, leaseId }).returning();
    await tx.update(conversations).set({ updatedAt: new Date() }).where(eq(conversations.id, conversation.id));
    return { row, generate: true };
  });
  if (!prepared.generate) {
    res.json(SendJeevMessageResponse.parse(messageJson(prepared.row)));
    return;
  }
  try {
    // Use the database timestamp at its original precision. A JavaScript Date can
    // round down to before the saved question, leaving a first chat with no user turn.
    const previous = (await db.select({ content: messages.content, reply: messages.reply }).from(messages).where(and(
      eq(messages.conversationId, params.data.id), eq(messages.replyState, "ready"),
      policyId ? eq(messages.policyId, policyId) : isNull(messages.policyId),
      sql`(${messages.createdAt}, ${messages.id}) < (SELECT created_at, id FROM ${messages} WHERE id = ${prepared.row.id})`,
    )).orderBy(desc(messages.createdAt), desc(messages.id)).limit(11)).reverse();
    const relevant = previous.filter(entry => includePromptInHistory(entry.content, entry.reply));
    const hasPriorRelevantTurn = relevant.some(entry => promptInScope(entry.content));
    if (!promptInScope(content, { followup: hasPriorRelevantTurn })) {
      req.log.info({ event: "chat_scope_rejected" }, "Dashboard question outside supported scope");
      await db.update(messages).set({ reply: OUT_OF_SCOPE_MESSAGE, replyState: "ready", updatedAt: new Date() })
        .where(and(eq(messages.id, prepared.row.id), eq(messages.leaseId, leaseId)));
    } else {
    const result = await dashboardReply(params.data.id, ownerId, policyId, prepared.row.content, relevant);
    await db.update(messages).set({ ...result, replyState: "ready", updatedAt: new Date() })
      .where(and(eq(messages.id, prepared.row.id), eq(messages.leaseId, leaseId)));
    }
  } catch (error) {
    req.log.warn({ errorType: error instanceof Error ? error.name : "Unknown" }, "Jeeves reply unavailable; conversation message saved");
    await db.update(messages).set({ replyState: "error", updatedAt: new Date() })
      .where(and(eq(messages.id, prepared.row.id), eq(messages.leaseId, leaseId)));
  }
  const [current] = await db.select().from(messages).where(and(
    eq(messages.id, prepared.row.id), eq(messages.conversationId, params.data.id),
  ));
  res.json(SendJeevMessageResponse.parse(messageJson(current)));
});

const handleChatError: ErrorRequestHandler = (error, req, res, next) => {
  if (error instanceof ClaimRequestError) {
    res.status(error.status).json({ error: error.message });
    return;
  }
  req.log.error({ errorType: error instanceof Error ? error.name : "Unknown" }, "Jeeves chat request failed");
  if (res.headersSent) { next(error); return; }
  res.status(500).json({ error: "Chat is unavailable. Your message may have been saved; retry safely." });
};
router.use(handleChatError);

export default router;
