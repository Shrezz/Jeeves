import assert from "node:assert/strict";
import test from "node:test";
import { workerTracingEnv } from "./workflow-tracing";

test("only opted-in, configured workers receive Langfuse credentials", () => {
  const env = { LANGFUSE_TRACING_ENABLED: "true", LANGFUSE_PUBLIC_KEY: "public", LANGFUSE_SECRET_KEY: "secret",
    LANGFUSE_BASE_URL: "https://example.test", LANGFUSE_CAPTURE_SYNTHETIC_CONTENT: "true", CLERK_SECRET_KEY: "private" };
  assert.deepEqual(workerTracingEnv(env), { LANGFUSE_TRACING_ENABLED: "true", LANGFUSE_PUBLIC_KEY: "public",
    LANGFUSE_SECRET_KEY: "secret", LANGFUSE_BASE_URL: "https://example.test" });
  for (const overrides of [{ LANGFUSE_TRACING_ENABLED: "false" }, { LANGFUSE_SECRET_KEY: "" }]) {
    assert.deepEqual(workerTracingEnv({ ...env, ...overrides }), { LANGFUSE_TRACING_ENABLED: "false" });
  }
});
