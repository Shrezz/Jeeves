import assert from "node:assert/strict";
import test from "node:test";
import { workerTracingEnv } from "./workflow-tracing";

test("only opted-in, configured workers receive Langfuse credentials", () => {
  const env = { LANGFUSE_TRACING_ENABLED: "true", LANGFUSE_PUBLIC_KEY: "public", LANGFUSE_SECRET_KEY: "secret",
    LANGFUSE_BASE_URL: "https://example.test", LANGFUSE_CAPTURE_SYNTHETIC_CONTENT: "true", CLERK_SECRET_KEY: "private" };
  assert.deepEqual(workerTracingEnv(env), { LANGFUSE_TRACING_ENABLED: "true", LANGFUSE_PUBLIC_KEY: "public",
    LANGFUSE_SECRET_KEY: "secret", LANGFUSE_BASE_URL: "https://example.test",
    LANGFUSE_TRACING_ENVIRONMENT: "development", LANGFUSE_RELEASE: "local" });
  for (const overrides of [{ LANGFUSE_TRACING_ENABLED: "false" }, { LANGFUSE_SECRET_KEY: "" }]) {
    assert.deepEqual(workerTracingEnv({ ...env, ...overrides }), { LANGFUSE_TRACING_ENABLED: "false" });
  }
});

test("production refuses silent tracing gaps and content capture", async () => {
  const { validateProductionObservability } = await import("./workflow-tracing");
  const env = { NODE_ENV: "production", CLAIM_CHAT_ROOT: "/runtime", LOCAL_RAG_ROOT: "/rag", LOCAL_RAG_DATA_DIR: "/persistent/rag", LANGFUSE_TRACING_ENABLED: "true",
    LANGFUSE_TRACING_ENVIRONMENT: "production", LANGFUSE_RELEASE: "build-123", LANGFUSE_BASE_URL: "https://example.test",
    LANGFUSE_PUBLIC_KEY: "public", LANGFUSE_SECRET_KEY: "secret" };
  assert.doesNotThrow(() => validateProductionObservability(env));
  assert.throws(() => validateProductionObservability({ NODE_ENV: "development", LANGFUSE_TRACING_ENABLED: "true" }));
  for (const change of [{ CLAIM_CHAT_ROOT: "" }, { LOCAL_RAG_ROOT: "" }, { LOCAL_RAG_DATA_DIR: "" }, { LANGFUSE_RELEASE: "local" }, { LANGFUSE_TRACING_ENVIRONMENT: "development" },
    { LANGFUSE_CAPTURE_SYNTHETIC_CONTENT: "true" }, { LANGFUSE_BASE_URL: "http://example.test" }]) {
    assert.throws(() => validateProductionObservability({ ...env, ...change }));
  }
  assert.equal(workerTracingEnv(env).LANGFUSE_RELEASE, "build-123");
  assert.equal(workerTracingEnv(env).LANGFUSE_TRACING_ENVIRONMENT, "production");
});
