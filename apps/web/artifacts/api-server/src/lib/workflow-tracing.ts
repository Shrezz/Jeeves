/** Only opted-in server workers receive export credentials; never pass them to Vite, RAG or Ollama. */
export function workerTracingEnv(env: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  if (env.LANGFUSE_TRACING_ENABLED?.toLowerCase() !== "true" ||
      !env.LANGFUSE_PUBLIC_KEY || !env.LANGFUSE_SECRET_KEY) return { LANGFUSE_TRACING_ENABLED: "false" };
  return {
    LANGFUSE_TRACING_ENABLED: "true",
    LANGFUSE_PUBLIC_KEY: env.LANGFUSE_PUBLIC_KEY,
    LANGFUSE_SECRET_KEY: env.LANGFUSE_SECRET_KEY,
    ...(env.LANGFUSE_BASE_URL ? { LANGFUSE_BASE_URL: env.LANGFUSE_BASE_URL } : {}),
  };
}
