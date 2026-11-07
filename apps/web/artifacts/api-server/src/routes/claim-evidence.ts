import { randomUUID } from "node:crypto";
import { pipeline } from "node:stream/promises";
import { Router, type IRouter } from "express";
import { getAuth } from "@clerk/express";
import { and, count, eq, gt } from "drizzle-orm";
import { db, claimEvidenceTable, claimsTable } from "@workspace/db";
import {
  InitiateClaimEvidenceBody, InitiateClaimEvidenceParams, InitiateClaimEvidenceResponse,
  CompleteClaimEvidenceParams, CompleteClaimEvidenceResponse, DownloadClaimEvidenceParams,
} from "@workspace/api-zod";
import { ObjectNotFoundError, ObjectStorageService } from "../lib/objectStorage";
import { setObjectAclPolicy } from "../lib/objectAcl";
import { ClaimRequestError, ownedClaim, serializeEvidence } from "../lib/claims";
import { EVIDENCE_UPLOAD_LIFETIME, MAX_EVIDENCE_BYTES, copyVideoEvidence, readEvidence, validEvidenceName } from "../lib/claim-evidence";

const router: IRouter = Router();
const storage = new ObjectStorageService();

router.post("/claims/:id/evidence/uploads", async (req, res): Promise<void> => {
  const params = InitiateClaimEvidenceParams.safeParse(req.params);
  const body = InitiateClaimEvidenceBody.safeParse(req.body);
  if (!params.success || !body.success || !validEvidenceName(body.data.fileName, body.data.contentType)) {
    throw new ClaimRequestError(400, "Choose a PDF/JPG/PNG up to 20 MB, or MP4/WebM/MOV video up to 100 MB.");
  }
  if (!body.data.contentType.startsWith("video/") && body.data.size > MAX_EVIDENCE_BYTES) {
    throw new ClaimRequestError(400, "Photos and PDFs must be 20 MB or smaller. Videos can be up to 100 MB.");
  }
  const ownerId = getAuth(req).userId!;
  await ownedClaim(params.data.id, ownerId);
  const [{ value: pending }] = await db.select({ value: count() }).from(claimEvidenceTable)
    .innerJoin(claimsTable, eq(claimEvidenceTable.claimId, claimsTable.id)).where(and(
      eq(claimsTable.ownerId, ownerId), eq(claimEvidenceTable.status, "pending"),
      gt(claimEvidenceTable.createdAt, new Date(Date.now() - EVIDENCE_UPLOAD_LIFETIME)),
    ));
  if (pending >= 10) { res.status(429).json({ error: "Too many unfinished uploads. Wait 15 minutes and try again." }); return; }
  const uploadURL = await storage.getObjectEntityUploadURL();
  const [evidence] = await db.insert(claimEvidenceTable).values({
    claimId: params.data.id, fileName: body.data.fileName.trim(), size: body.data.size,
    contentType: body.data.contentType, objectPath: storage.normalizeObjectEntityPath(uploadURL),
  }).returning();
  res.status(201).json(InitiateClaimEvidenceResponse.parse({ id: evidence.id, uploadURL }));
});

router.post("/claims/:id/evidence/:evidenceId/complete", async (req, res): Promise<void> => {
  const params = CompleteClaimEvidenceParams.safeParse(req.params);
  if (!params.success) throw new ClaimRequestError(400, "Invalid claim or evidence ID.");
  const ownerId = getAuth(req).userId!;
  await ownedClaim(params.data.id, ownerId);
  const condition = and(eq(claimEvidenceTable.claimId, params.data.id), eq(claimEvidenceTable.id, params.data.evidenceId));
  const [evidence] = await db.select().from(claimEvidenceTable).where(condition);
  if (!evidence) throw new ClaimRequestError(404, "Evidence not found.");
  if (evidence.status === "saved") { res.json(CompleteClaimEvidenceResponse.parse(serializeEvidence(evidence))); return; }
  if (evidence.createdAt.getTime() < Date.now() - EVIDENCE_UPLOAD_LIFETIME) throw new ClaimRequestError(400, "This upload expired. Choose the file again.");
  try {
    const staging = await storage.getObjectEntityFile(evidence.objectPath);
    const objectId = randomUUID();
    const path = `/objects/claim-evidence/${objectId}`;
    const permanent = staging.bucket.file(
      staging.name.slice(0, staging.name.lastIndexOf("/uploads/")) + `/claim-evidence/${objectId}`,
    );
    try {
      if (evidence.contentType.startsWith("video/")) {
        await copyVideoEvidence(staging, permanent, evidence.size, evidence.contentType);
      } else {
        const bytes = await readEvidence(staging, evidence.size, evidence.contentType);
        await permanent.save(bytes, {
          resumable: false, validation: "crc32c",
          metadata: { contentType: evidence.contentType, cacheControl: "private, no-store" },
        });
      }
      await setObjectAclPolicy(permanent, { owner: ownerId, visibility: "private" });
      const result = await db.transaction(async (tx) => {
        const [claim] = await tx.select().from(claimsTable).where(and(
          eq(claimsTable.id, evidence.claimId), eq(claimsTable.ownerId, ownerId),
        )).for("update");
        if (!claim) throw new ClaimRequestError(404, "Claim not found.");
        const [saved] = await tx.update(claimEvidenceTable).set({ status: "saved", objectPath: path })
          .where(and(condition, eq(claimEvidenceTable.status, "pending"))).returning();
        if (!saved) {
          const [winner] = await tx.select().from(claimEvidenceTable).where(condition);
          return { saved: winner, used: false };
        }
        await tx.update(claimsTable).set({
          latestUpdate: `Evidence added: ${evidence.fileName}`, updatedAt: new Date(),
          status: claim.status === "Draft" ? "Gathering evidence" : claim.status,
        }).where(eq(claimsTable.id, claim.id));
        return { saved, used: true };
      });
      if (!result.used) await permanent.delete({ ignoreNotFound: true }).catch(() => {});
      res.json(CompleteClaimEvidenceResponse.parse(serializeEvidence(result.saved)));
      await staging.delete({ ignoreNotFound: true }).catch(() => {});
    } catch (error) {
      await permanent.delete({ ignoreNotFound: true }).catch(() => {});
      throw error;
    }
  } catch (error) {
    if (error instanceof ObjectNotFoundError) {
      // A concurrent successful completion may have removed the staging file.
      const [saved] = await db.select().from(claimEvidenceTable).where(condition);
      if (saved?.status === "saved") { res.json(CompleteClaimEvidenceResponse.parse(serializeEvidence(saved))); return; }
      throw new ClaimRequestError(400, "The upload has not finished. Choose the file and try again.");
    }
    throw error;
  }
});

router.get("/claims/:id/evidence/:evidenceId/document", async (req, res): Promise<void> => {
  const params = DownloadClaimEvidenceParams.safeParse(req.params);
  if (!params.success) throw new ClaimRequestError(400, "Invalid claim or evidence ID.");
  await ownedClaim(params.data.id, getAuth(req).userId!);
  const [evidence] = await db.select().from(claimEvidenceTable).where(and(
    eq(claimEvidenceTable.id, params.data.evidenceId), eq(claimEvidenceTable.claimId, params.data.id),
    eq(claimEvidenceTable.status, "saved"),
  ));
  if (!evidence) throw new ClaimRequestError(404, "Evidence not found.");
  try {
    const file = await storage.getObjectEntityFile(evidence.objectPath);
    res.set({
      "Content-Type": evidence.contentType, "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
      "Content-Disposition": `attachment; filename="evidence"; filename*=UTF-8''${encodeURIComponent(evidence.fileName).replace(/['()]/g, (c) => `%${c.charCodeAt(0).toString(16)}`)}`,
    });
    await pipeline(file.createReadStream(), res);
  } catch (error) {
    if (res.headersSent) return;
    if (error instanceof ObjectNotFoundError) throw new ClaimRequestError(404, "Evidence file is unavailable.");
    throw error;
  }
});

export default router;
