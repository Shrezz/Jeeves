/** Configuration for the isolated, loopback-only development stack. */
export const LOCAL_WEB_URL = "http://localhost:5173";
export const LOCAL_DATABASE_URL = "postgresql://jeeves:jeeves-local-only@127.0.0.1:54329/jeeves_local";

export function localConfig(env) {
  for (const [name, prefix] of [["CLERK_PUBLISHABLE_KEY", "pk_test_"], ["CLERK_SECRET_KEY", "sk_test_"]]) {
    const value = env[name] || "";
    if (!value.startsWith(prefix) || value.length <= prefix.length || /\s|replace_me/.test(value)) {
      throw new Error(`Set ${name} to a Clerk development key in apps/web/.env.local.`);
    }
  }
  const provider = env.CLAIM_CHAT_PROVIDER || "ollama";
  if (!["ollama", "nebius"].includes(provider)) throw new Error("Set CLAIM_CHAT_PROVIDER to ollama or nebius.");
  if (provider === "nebius") {
    for (const key of ["NEBIUS_API_KEY", "NEBIUS_GENERATOR_MODEL", "NEBIUS_REVIEWER_MODEL"]) {
      if (!env[key]?.trim() || /replace[_-]?me/i.test(env[key])) throw new Error(`Nebius mode requires ${key} in apps/web/.env.local.`);
    }
    if (env.NEBIUS_GENERATOR_MODEL.trim() === env.NEBIUS_REVIEWER_MODEL.trim()) {
      throw new Error("Choose distinct NEBIUS_GENERATOR_MODEL and NEBIUS_REVIEWER_MODEL IDs.");
    }
  }
  return {
    ...env,
    NODE_ENV: "development",
    HOST: "127.0.0.1",
    DATABASE_URL: LOCAL_DATABASE_URL,
    CLERK_AUTHORIZED_PARTIES: LOCAL_WEB_URL,
    VITE_CLERK_PUBLISHABLE_KEY: env.CLERK_PUBLISHABLE_KEY,
    // Development instances connect directly to Clerk, without the Replit proxy.
    VITE_CLERK_PROXY_URL: "",
    LOCAL_API_PROXY_TARGET: "http://127.0.0.1:8080",
    LOCAL_WEB_HOST: "127.0.0.1",
    BASE_PATH: "/",
    CLAIM_CHAT_PROVIDER: provider,
    DASHBOARD_CHAT_PROVIDER: provider,
    OLLAMA_MODEL: env.OLLAMA_MODEL || "gemma4:12b",
    // No automatic fallback to a hosted model.
    AI_INTEGRATIONS_OPENAI_BASE_URL: "",
    AI_INTEGRATIONS_OPENAI_API_KEY: "",
  };
}

/** Vite needs only the public key, not backend credentials or unrelated secrets. */
export function frontendConfig(env) {
  const safe = {};
  for (const name of ["PATH", "HOME", "USERPROFILE", "SystemRoot", "TEMP", "TMP", "TMPDIR", "TERM", "FORCE_COLOR"]) {
    if (env[name]) safe[name] = env[name];
  }
  return {
    ...safe,
    NODE_ENV: "development",
    VITE_CLERK_PUBLISHABLE_KEY: env.VITE_CLERK_PUBLISHABLE_KEY,
    VITE_CLERK_PROXY_URL: "",
    LOCAL_API_PROXY_TARGET: env.LOCAL_API_PROXY_TARGET,
    LOCAL_WEB_HOST: env.LOCAL_WEB_HOST,
    BASE_PATH: "/",
    VITE_LOCAL_POLICY_SEARCH: "1",
    VITE_KEENABLE_SEARCH_ENABLED: env.KEENABLE_SEARCH_ENABLED?.toLowerCase() === "true" ? "true" : "false",
    PORT: "5173",
  };
}
