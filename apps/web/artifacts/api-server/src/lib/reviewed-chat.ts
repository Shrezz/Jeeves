import { execFile } from "node:child_process";
import path from "node:path";
import type { ClaimReviewResponseInput } from "@workspace/api-zod";
import { ClaimRequestError } from "./claim-errors";

/** Only the authenticated API supplies identity and run binding. No graph state comes from a browser. */
export async function runClaimGraph(owner: string, claimId: string, runId: string, response?: ClaimReviewResponseInput) {
  const root = process.env.CLAIM_CHAT_ROOT!;
  const mode = process.env.CLAIM_CHAT_PROVIDER ?? "ollama";
  const env: NodeJS.ProcessEnv = { CLAIM_CHAT_PROVIDER: mode, LANGFUSE_TRACING_ENABLED: "false" };
  for (const key of ["PATH", "HOME", "DATABASE_URL", "LOCAL_RAG_ROOT", "LOCAL_RAG_DATA_DIR",
    ...(mode === "nebius" ? ["NEBIUS_API_KEY", "NEBIUS_GENERATOR_MODEL", "NEBIUS_REVIEWER_MODEL"] : ["OLLAMA_MODEL"])]) {
    if (process.env[key]) env[key] = process.env[key];
  }
  const python = path.join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  const raw = await new Promise<string>((resolve, reject) => {
    const child = execFile(python, ["-m", "app.services.ui_workflow"], {
      cwd: root, env, timeout: 280_000, killSignal: "SIGKILL", maxBuffer: 256 * 1024,
    }, (error, stdout) => error ? reject(new Error("Claim workflow unavailable")) : resolve(stdout));
    child.stdin?.on("error", () => {});
    child.stdin?.end(JSON.stringify({ owner, claimId, runId, response }));
  });
  const result = JSON.parse(raw);
  if (typeof result.conflict === "string") throw new ClaimRequestError(409, result.conflict);
  if (result.ok !== true) throw new Error("Invalid workflow response");
}
