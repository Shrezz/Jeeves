/** Start the local UI and API after checking Clerk keys and migrating the UI DB. */
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { loadEnvFile } from "node:process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { frontendConfig, localConfig, LOCAL_WEB_URL } from "./local-config.mjs";

const web = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const root = path.resolve(web, "../..");
const api = path.join(root, "apps/api");
const python = path.join(api, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const children = new Set();

function run(command, args, cwd, env) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd, env, stdio: "inherit" });
    child.once("error", reject);
    child.once("exit", (code) => code === 0 ? resolve() : reject(new Error(`${path.basename(command)} failed (${code}).`)));
  });
}

function stop(code = 0) {
  process.exitCode = code;
  for (const child of children) child.kill("SIGTERM");
}

function serve(command, args, cwd, env) {
  const child = spawn(command, args, { cwd, env, stdio: "inherit" });
  children.add(child);
  child.once("error", (error) => { console.error(error.message); stop(1); });
  child.once("exit", (code) => { children.delete(child); stop(code ?? 0); });
}

async function main() {
  const envFile = path.join(web, ".env.local");
  if (!existsSync(envFile)) throw new Error("Copy apps/web/.env.local.example to .env.local and add your Clerk development keys.");
  loadEnvFile(envFile);
  const env = {
    ...localConfig(process.env),
    CLAIM_CHAT_ROOT: api,
    LOCAL_RAG_ROOT: path.join(root, "RAG"),
    LOCAL_RAG_DATA_DIR: path.join(root, "data/generated/local-rag"),
  };
  if (process.argv.includes("--check")) {
    console.log("Local configuration is present. Clerk credentials still need live verification.");
    return;
  }
  if (!existsSync(python)) throw new Error("Create apps/api/.venv and install requirements-db.txt before starting. See docs/local-development.md.");
  const ragPython = path.join(env.LOCAL_RAG_ROOT, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  if (!existsSync(ragPython)) throw new Error("Set up RAG/.venv with RAG/requirements.txt first. See docs/local-development.md.");
  await run("docker", ["compose", "-f", "compose.local.yml", "up", "-d", "--wait"], root, env);
  await run(python, ["-m", "app.db.migrate", "--directory", "../web/lib/db/migrations"], api, env);
  await run(python, ["-m", "app.services.ui_workflow", "--setup"], api, env);
  await run(pnpm, ["--filter", "@workspace/api-server", "run", "build"], web, env);
  process.on("SIGINT", () => stop());
  process.on("SIGTERM", () => stop());
  serve(process.execPath, ["--enable-source-maps", "dist/index.mjs"], path.join(web, "artifacts/api-server"), { ...env, PORT: "8080" });
  // Launch Vite directly so shutdown reaches the server, rather than a pnpm wrapper.
  serve(process.execPath, [path.join(web, "artifacts/claimwise/node_modules/vite/bin/vite.js"), "--config", "vite.config.ts"], path.join(web, "artifacts/claimwise"), frontendConfig(env));
  console.log(`Local UI: ${LOCAL_WEB_URL}. Ctrl+C stops UI/API; PostgreSQL data remains on disk.`);
}

main().catch((error) => { console.error(error.message); stop(1); });
