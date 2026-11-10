import { logger } from "./logger";
import { execFile } from "node:child_process";
import path from "node:path";
import { GetPolicyDeclarationsResponse } from "@workspace/api-zod";

/** The declarations reader needs only the immutable original, not a vector index. */
export function readDeclarations(pdf: Buffer) {
  const root = process.env.LOCAL_RAG_ROOT!;
  const python = path.join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  return new Promise<ReturnType<typeof GetPolicyDeclarationsResponse.parse>>((resolve, reject) => {
    const child = execFile(python, ["-I", path.join(root, "policy_rag/declarations.py")], {
      timeout: 15_000, killSignal: "SIGKILL", maxBuffer: 256 * 1024, env: { PATH: process.env.PATH },
    }, (error, stdout) => {
      if (error) { logger.error({ event: "worker_failed", worker: "declarations", killed: error.killed ?? false }, "Declarations reader failed"); reject(new Error("Policy declarations could not be read")); return; }
      try { resolve(GetPolicyDeclarationsResponse.parse(JSON.parse(stdout))); }
      catch { logger.error({ event: "worker_invalid_response", worker: "declarations" }, "Declarations reader returned invalid data"); reject(new Error("Invalid policy declarations response")); }
    });
    child.stdin?.on("error", () => { /* Process errors are handled above. */ });
    child.stdin?.end(pdf);
  });
}
