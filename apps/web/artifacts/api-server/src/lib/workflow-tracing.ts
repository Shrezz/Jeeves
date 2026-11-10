/** Only opted-in server workers receive export credentials; never pass them to Vite or Ollama. */
export function workerTracingEnv(env: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  if (env.LANGFUSE_TRACING_ENABLED?.toLowerCase() !== "true" ||
      !env.LANGFUSE_PUBLIC_KEY || !env.LANGFUSE_SECRET_KEY) return { LANGFUSE_TRACING_ENABLED: "false" };
  return {
    LANGFUSE_TRACING_ENABLED: "true",
    LANGFUSE_PUBLIC_KEY: env.LANGFUSE_PUBLIC_KEY,
    LANGFUSE_SECRET_KEY: env.LANGFUSE_SECRET_KEY,
    LANGFUSE_TRACING_ENVIRONMENT: env.LANGFUSE_TRACING_ENVIRONMENT || "development",
    LANGFUSE_RELEASE: env.LANGFUSE_RELEASE || "local",
    ...(env.LANGFUSE_BASE_URL ? { LANGFUSE_BASE_URL: env.LANGFUSE_BASE_URL } : {}),
  };
}

/** Deployment gate: production must use the instrumented worker path. */
export function validateProductionObservability(env: NodeJS.ProcessEnv): void {
  if (env.LANGFUSE_TRACING_ENABLED?.toLowerCase() === "true" && !env.CLAIM_CHAT_ROOT?.trim()) {
    throw new Error("Tracing requires the instrumented CLAIM_CHAT_ROOT runtime");
  }
  if (env.NODE_ENV !== "production") return;
  const required = ["CLAIM_CHAT_ROOT", "LOCAL_RAG_ROOT", "LOCAL_RAG_DATA_DIR", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL", "LANGFUSE_RELEASE"];
  for (const name of required) {
    if (!env[name]?.trim()) throw new Error(`Production requires ${name}`);
  }
  if (env.LANGFUSE_TRACING_ENABLED !== "true" || env.LANGFUSE_TRACING_ENVIRONMENT !== "production") {
    throw new Error("Production requires enabled tracing in the production environment");
  }
  const endpoint = new URL(env.LANGFUSE_BASE_URL!);
  if (endpoint.protocol !== "https:" || endpoint.username || endpoint.password) {
    throw new Error("Production tracing requires an HTTPS endpoint without embedded credentials");
  }
  if (env.LANGFUSE_RELEASE === "local" || env.LANGFUSE_CAPTURE_SYNTHETIC_CONTENT === "true") {
    throw new Error("Production requires a build release and metadata-only tracing");
  }
}
