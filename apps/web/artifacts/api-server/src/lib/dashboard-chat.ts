import { logger } from "./logger";
import { execFile } from "node:child_process";
import path from "node:path";
import { workerTracingEnv } from "./workflow-tracing";
import { SendJeevMessageResponse } from "@workspace/api-zod";

const resultSchema = SendJeevMessageResponse.pick({ route: true, sources: true, reply: true })
  .required({ route: true });

type Turn = { content: string; reply: string | null };

export async function dashboardReply(conversationId: string, owner: string, policyId: string | null, question: string, previous: Turn[]) {
  const root = process.env.CLAIM_CHAT_ROOT;
  if (!root) throw new Error("Dashboard routing runtime is not configured");
  const provider = process.env.DASHBOARD_CHAT_PROVIDER || process.env.CLAIM_CHAT_PROVIDER || "ollama";
  const env: NodeJS.ProcessEnv = { CLAIM_CHAT_PROVIDER: provider, ...workerTracingEnv(process.env) };
  for (const key of ["PATH", "HOME", "LOCAL_RAG_ROOT", "LOCAL_RAG_DATA_DIR",
    ...(provider === "openai" ? ["AI_INTEGRATIONS_OPENAI_BASE_URL", "AI_INTEGRATIONS_OPENAI_API_KEY"] : provider === "nebius" ? ["NEBIUS_API_KEY", "NEBIUS_GENERATOR_MODEL", "NEBIUS_REVIEWER_MODEL"] : ["OLLAMA_MODEL"])]) {
    if (process.env[key]) env[key] = process.env[key];
  }
  const python = path.join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  const raw = await new Promise<string>((resolve, reject) => {
    // The intake graph can read the selected index but has no database credentials or claim write tools.
    const child = execFile(python, ["-m", "app.services.dashboard_workflow"], {
      cwd: root, env, timeout: 280_000, killSignal: "SIGKILL", maxBuffer: 256 * 1024,
    }, (error, stdout, stderr) => {
      if (/telemetry_(?:export_failed|flush_(?:failed|timeout))/.test(stderr)) logger.warn({ event: "telemetry_export_failed", worker: "dashboard-chat.ts" }, "Telemetry export incomplete");
      if (error) { logger.error({ event: "worker_failed", worker: "dashboard-chat.ts", killed: error.killed ?? false }, "Worker failed"); reject(new Error("Dashboard workflow unavailable")); }
      else resolve(stdout);
    });
    child.stdin?.on("error", () => {});
    child.stdin?.end(JSON.stringify({ conversationId, owner, policyId, question,
      previous: previous.slice(-5).map(turn => ({content: turn.content.slice(0, 1200), reply: turn.reply?.slice(0, 900)})) }));
  });
  const value = JSON.parse(raw);
  const result = resultSchema.parse({ ...value, reply: value.content });
  if (!result.reply?.trim() || result.sources.some(s => !policyId || !s.chunkId.startsWith(policyId + ":"))) {
    throw new Error("Invalid dashboard response");
  }
  return result;
}
