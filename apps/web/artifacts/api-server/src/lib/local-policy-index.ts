import { execFile } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { and, eq } from "drizzle-orm";
import { SearchPolicyResponse } from "@workspace/api-zod";
import { db, policiesTable, policyDocumentsTable, type StoredPolicy } from "@workspace/db";

const active = new Map<string, Promise<StoredPolicy>>();
// Embedded Chroma is opened by one short-lived process at a time in the local demo.
let tail: Promise<unknown> = Promise.resolve();

function worker(request: object): Promise<unknown> {
  const root = process.env.LOCAL_RAG_ROOT!;
  const python = path.join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  const task = tail.then(() => new Promise<unknown>((resolve, reject) => {
    const child = execFile(python, ["-m", "policy_rag.local_worker"], {
      cwd: root, timeout: 180_000, killSignal: "SIGKILL", maxBuffer: 2 * 1024 * 1024,
      env: { PATH: process.env.PATH, HOME: process.env.HOME, LOCAL_RAG_DATA_DIR: process.env.LOCAL_RAG_DATA_DIR,
        POLICY_RAG_TRACE: "0", ANONYMIZED_TELEMETRY: "False", TOKENIZERS_PARALLELISM: "false" },
    }, (error, stdout) => {
      if (error) { reject(new Error("Local policy worker failed")); return; }
      try { resolve(JSON.parse(stdout)); } catch { reject(new Error("Invalid worker response")); }
    });
    child.stdin?.on("error", () => { /* execFile reports process failures */ });
    child.stdin?.end(JSON.stringify(request));
  }));
  tail = task.catch(() => undefined);
  return task;
}

export function isLocalPolicy(policy: StoredPolicy) {
  return policy.objectPath === "local-db:" + policy.id;
}

export async function readLocalPdf(id: string, owner: string) {
  const [stored] = await db.select({ content: policyDocumentsTable.content }).from(policyDocumentsTable)
    .innerJoin(policiesTable, eq(policiesTable.id, policyDocumentsTable.policyId))
    .where(and(eq(policiesTable.id, id), eq(policiesTable.ownerId, owner)));
  return stored?.content;
}

export function indexLocalPolicy(policy: StoredPolicy): Promise<StoredPolicy> {
  if (policy.ingestionStatus === "ready") return Promise.resolve(policy);
  const current = active.get(policy.id);
  if (current) return current;
  const task = runIndex(policy).finally(() => active.delete(policy.id));
  active.set(policy.id, task);
  return task;
}

async function runIndex(policy: StoredPolicy): Promise<StoredPolicy> {
  const owned = and(eq(policiesTable.id, policy.id), eq(policiesTable.ownerId, policy.ownerId));
  await db.update(policiesTable).set({ ingestionStatus: "processing", indexedChunks: 0 }).where(owned);
  let scratch: string | undefined;
  try {
    const content = await readLocalPdf(policy.id, policy.ownerId);
    if (!content) throw new Error("Missing PDF");
    scratch = await mkdtemp(path.join(tmpdir(), "jeeves-index-"));
    const pdf = path.join(scratch, "policy.pdf");
    await writeFile(pdf, content, { mode: 0o600 });
    const result = await worker({ operation: "index", owner: policy.ownerId, policy: policy.id, pdf });
    if (!result || typeof result !== "object" || !("count" in result) ||
        typeof result.count !== "number" || !Number.isSafeInteger(result.count) || result.count < 1) throw new Error("Empty index");
    const count = result.count;
    const [ready] = await db.update(policiesTable).set({ ingestionStatus: "ready", indexedChunks: count }).where(owned).returning();
    return ready;
  } catch {
    const [failed] = await db.update(policiesTable).set({ ingestionStatus: "failed", indexedChunks: 0 }).where(owned).returning();
    return failed;
  } finally {
    if (scratch) await rm(scratch, { recursive: true, force: true });
  }
}

export async function searchLocalPolicy(policy: StoredPolicy, question: string, forChat = false) {
  return SearchPolicyResponse.parse(await worker({ operation: "search", owner: policy.ownerId, policy: policy.id, question, forChat }));
}
