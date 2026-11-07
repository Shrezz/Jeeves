import express, { Router } from "express";
import { getAuth } from "@clerk/express";
import { and, eq } from "drizzle-orm";
import { GetPolicyDeclarationsParams, SearchPolicyParams, SearchPolicyBody } from "@workspace/api-zod";
import { db, policiesTable, policyDocumentsTable } from "@workspace/db";
import { InvalidPolicyDocument, MAX_POLICY_BYTES, validatePdfBytes } from "../lib/policyDocuments";
import { indexLocalPolicy, isLocalPolicy, searchLocalPolicy } from "../lib/local-policy-index";
import { serializePolicy } from "../lib/serialize-policy";
import { readDeclarations } from "../lib/local-policy-declarations";

export const localPolicies = Router();
localPolicies.get("/policies/:id/declarations", async (req, res) => {
  res.set("Cache-Control", "private, no-store");
  const id = GetPolicyDeclarationsParams.safeParse(req.params);
  if (!id.success) { res.sendStatus(400); return; }
  const [document] = await db.select({ content: policyDocumentsTable.content }).from(policyDocumentsTable)
    .innerJoin(policiesTable, eq(policiesTable.id, policyDocumentsTable.policyId))
    .where(and(eq(policiesTable.id, id.data.id), eq(policiesTable.ownerId, getAuth(req).userId!),
      eq(policiesTable.objectPath, "local-db:" + id.data.id), eq(policiesTable.status, "saved")));
  if (!document) { res.sendStatus(404); return; }
  res.json(await readDeclarations(document.content));
});

localPolicies.put("/policies/:id/content", express.raw({ type: "application/pdf", limit: MAX_POLICY_BYTES, inflate: false }), async (req, res) => {
  const id = SearchPolicyParams.safeParse(req.params);
  if (!id.success) { res.sendStatus(400); return; }
  const owner = getAuth(req).userId!;
  const result = await db.transaction(async tx => {
    const [policy] = await tx.select().from(policiesTable).where(and(eq(policiesTable.id, id.data.id), eq(policiesTable.ownerId, owner))).for("update");
    if (!policy || !isLocalPolicy(policy)) return 404;
    if (policy.status !== "pending" || Date.now() - policy.createdAt.getTime() > 900_000) return 409;
    if (!Buffer.isBuffer(req.body)) return 415;
    try { validatePdfBytes(req.body, policy.size); }
    catch (error) { if (error instanceof InvalidPolicyDocument) return 400; throw error; }
    const [saved] = await tx.insert(policyDocumentsTable).values({ policyId: policy.id, content: req.body })
      .onConflictDoNothing().returning({ id: policyDocumentsTable.policyId });
    if (!saved) {
      const [prior] = await tx.select().from(policyDocumentsTable).where(eq(policyDocumentsTable.policyId, policy.id));
      if (!prior.content.equals(req.body)) return 409;
    }
    return 204;
  });
  res.sendStatus(result);
});

localPolicies.post(["/policies/:id/search", "/policies/:id/index"], async (req, res) => {
  const id = SearchPolicyParams.safeParse(req.params);
  if (!id.success) { res.sendStatus(400); return; }
  const [policy] = await db.select().from(policiesTable).where(and(eq(policiesTable.id, id.data.id),
    eq(policiesTable.ownerId, getAuth(req).userId!), eq(policiesTable.status, "saved")));
  if (!policy || !isLocalPolicy(policy)) { res.sendStatus(404); return; }
  if (req.path.endsWith("/index")) { res.json(serializePolicy(await indexLocalPolicy(policy))); return; }
  const input = SearchPolicyBody.strict().safeParse(req.body);
  if (!input.success || !input.data.question.trim()) { res.status(400).json({ error: "Enter a question of up to 800 characters." }); return; }
  if (policy.ingestionStatus !== "ready") { res.status(409).json({ error: "This policy is not ready to search." }); return; }
  res.set("Cache-Control", "private, no-store").json(await searchLocalPolicy(policy, input.data.question));
});
