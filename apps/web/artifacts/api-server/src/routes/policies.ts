import { randomUUID } from "node:crypto";
import { pipeline } from "node:stream/promises";
import { Router, type IRouter } from "express";
import { getAuth } from "@clerk/express";
import { and, count, desc, eq, gt } from "drizzle-orm";
import { db, policiesTable, type StoredPolicy } from "@workspace/db";
import {
  CompletePolicyUploadBody, CompletePolicyUploadParams, CompletePolicyUploadResponse,
  DownloadPolicyDocumentParams, InitiatePolicyUploadBody, InitiatePolicyUploadResponse,
  ListPoliciesResponse,
} from "@workspace/api-zod";
import { ObjectNotFoundError, ObjectStorageService } from "../lib/objectStorage";
import { setObjectAclPolicy } from "../lib/objectAcl";
import { InvalidPolicyDocument, readPolicyPdf } from "../lib/policyDocuments";

import { serializePolicy as serialize } from "../lib/serialize-policy";
import { isLocalPolicy, readLocalPdf, indexLocalPolicy } from "../lib/local-policy-index";
import { localPolicies } from "./local-policies";

const router: IRouter = Router();
const storage = new ObjectStorageService();
const UPLOAD_LIFETIME_MS = 15 * 60 * 1000;

router.use((req, res, next) => {
  if (req.method !== "GET" && req.get("sec-fetch-site") === "cross-site") {
    res.status(403).json({ error: "Cross-site requests are not allowed." });
    return;
  }
  next();
});

if (process.env.LOCAL_RAG_ROOT) router.use(localPolicies);

router.get("/policies", async (req, res): Promise<void> => {
  const policies = await db.select().from(policiesTable).where(and(
    eq(policiesTable.ownerId, getAuth(req).userId!),
    eq(policiesTable.status, "saved"),
  )).orderBy(desc(policiesTable.createdAt));
  res.json(ListPoliciesResponse.parse(policies.map(serialize)));
});

router.post("/policies/uploads", async (req, res): Promise<void> => {
  const parsed = InitiatePolicyUploadBody.safeParse(req.body);
  if (!parsed.success || !parsed.data.fileName.trim() || /[\x00-\x1f\x7f]/.test(parsed.data.fileName)) {
    res.status(400).json({ error: "Choose a PDF file up to 20 MB with a valid filename." });
    return;
  }
  const ownerId = getAuth(req).userId!;
  const [{ value: pending }] = await db.select({ value: count() }).from(policiesTable).where(and(
    eq(policiesTable.ownerId, ownerId), eq(policiesTable.status, "pending"),
    gt(policiesTable.createdAt, new Date(Date.now() - UPLOAD_LIFETIME_MS)),
  ));
  if (pending >= 10) {
    res.status(429).json({ error: "Too many unfinished uploads. Please wait 15 minutes before trying again." });
    return;
  }
  const id = randomUUID();
  const local = Boolean(process.env.LOCAL_RAG_ROOT);
  const uploadURL = local ? `/api/policies/${id}/content` : await storage.getObjectEntityUploadURL();
  const [policy] = await db.insert(policiesTable).values({
    id, ownerId, fileName: parsed.data.fileName, size: parsed.data.size,
    objectPath: local ? "local-db:" + id : storage.normalizeObjectEntityPath(uploadURL),
    label: parsed.data.fileName.replace(/\.pdf$/i, "").slice(0, 120),
  }).returning();
  res.status(201).json(InitiatePolicyUploadResponse.parse({ id: policy.id, uploadURL }));
});

router.post("/policies/:id/complete", async (req, res): Promise<void> => {
  const params = CompletePolicyUploadParams.safeParse(req.params);
  const body = CompletePolicyUploadBody.safeParse(req.body);
  if (!params.success || !body.success || !body.data.label.trim()) {
    res.status(400).json({ error: "Enter a policy label and a valid, optional deductible." });
    return;
  }
  const ownerId = getAuth(req).userId!;
  const owned = and(eq(policiesTable.id, params.data.id), eq(policiesTable.ownerId, ownerId));
  const [policy] = await db.select().from(policiesTable).where(owned);
  if (!policy) {
    res.status(404).json({ error: "Policy not found." });
    return;
  }
  // Safe retry after an interrupted response, without uploading another copy.
  if (policy.status === "saved") {
    res.json(CompletePolicyUploadResponse.parse(serialize(policy)));
    return;
  }
  if (policy.createdAt.getTime() < Date.now() - UPLOAD_LIFETIME_MS) {
    res.status(400).json({ error: "This upload expired. Please choose the PDF and try again." });
    return;
  }
  if (isLocalPolicy(policy)) {
    if (!await readLocalPdf(policy.id, ownerId)) { res.status(400).json({ error: "Transfer the PDF before saving." }); return; }
    const [saved] = await db.update(policiesTable).set({ status: "saved", label: body.data.label.trim(),
      deductible: body.data.deductible == null ? null : body.data.deductible.toFixed(2) })
      .where(and(owned, eq(policiesTable.status, "pending"))).returning();
    const row = saved ?? (await db.select().from(policiesTable).where(owned))[0];
    res.json(CompletePolicyUploadResponse.parse(serialize(await indexLocalPolicy(row))));
    return;
  }
  try {
    const stagingFile = await storage.getObjectEntityFile(policy.objectPath);
    const bytes = await readPolicyPdf(stagingFile, policy.size);
    // A new, non-signed object prevents a still-valid staging URL from changing
    // an already-saved policy. Use a unique destination for concurrent attempts.
    const permanentId = randomUUID();
    const permanentPath = `/objects/policies/${permanentId}`;
    const permanentFile = stagingFile.bucket.file(
      stagingFile.name.slice(0, stagingFile.name.lastIndexOf("/uploads/")) + `/policies/${permanentId}`,
    );
    await permanentFile.save(bytes, {
      resumable: false, validation: "crc32c",
      metadata: { contentType: "application/pdf", cacheControl: "private, no-store" },
    });
    await setObjectAclPolicy(permanentFile, { owner: ownerId, visibility: "private" });
    let saved: StoredPolicy | undefined;
    try {
      [saved] = await db.update(policiesTable).set({
        objectPath: permanentPath, label: body.data.label.trim(),
        deductible: body.data.deductible == null ? null : body.data.deductible.toFixed(2),
        status: "saved",
      }).where(and(owned, eq(policiesTable.status, "pending"))).returning();
    } catch (error) {
      await permanentFile.delete({ ignoreNotFound: true }).catch(() => {});
      throw error;
    }
    if (!saved) {
      await permanentFile.delete({ ignoreNotFound: true });
      [saved] = await db.select().from(policiesTable).where(owned);
    }
    res.json(CompletePolicyUploadResponse.parse(serialize(saved!)));
    // Staging objects are private and no longer referenced by the database.
    await stagingFile.delete({ ignoreNotFound: true }).catch(() => {});
  } catch (error) {
    if (error instanceof InvalidPolicyDocument || error instanceof ObjectNotFoundError) {
      res.status(400).json({ error: error instanceof InvalidPolicyDocument
        ? error.message : "The upload has not finished. Please try again." });
      return;
    }
    throw error;
  }
});

router.get("/policies/:id/document", async (req, res): Promise<void> => {
  const params = DownloadPolicyDocumentParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: "Invalid policy ID." });
    return;
  }
  const [policy] = await db.select().from(policiesTable).where(and(
    eq(policiesTable.id, params.data.id), eq(policiesTable.ownerId, getAuth(req).userId!),
    eq(policiesTable.status, "saved"),
  ));
  if (!policy) {
    res.status(404).json({ error: "Policy not found." });
    return;
  }
  try {
    res.set({
      "Content-Type": "application/pdf",
      "Content-Disposition": `attachment; filename="policy.pdf"; filename*=UTF-8''${encodeURIComponent(policy.fileName).replace(/['()]/g, (character) => `%${character.charCodeAt(0).toString(16)}`)}`,
      "Cache-Control": "private, no-store",
      "X-Content-Type-Options": "nosniff",
    });
    if (isLocalPolicy(policy)) {
      const bytes = await readLocalPdf(policy.id, policy.ownerId);
      if (!bytes) { res.sendStatus(404); return; }
      res.send(bytes);
    } else {
      const file = await storage.getObjectEntityFile(policy.objectPath);
      await pipeline(file.createReadStream(), res);
    }
  } catch (error) {
    if (res.headersSent) return;
    if (error instanceof ObjectNotFoundError) {
      res.status(404).json({ error: "Policy document is unavailable." });
      return;
    }
    throw error;
  }
});

router.use((error: unknown, req: import("express").Request, res: import("express").Response, next: import("express").NextFunction) => {
  if (res.headersSent) { next(error); return; }
  req.log.error({ errorType: error instanceof Error ? error.name : "Unknown" }, "Policy request failed");
  res.status(500).json({ error: "We couldn't save or load your policy. Please try again." });
});

export default router;
