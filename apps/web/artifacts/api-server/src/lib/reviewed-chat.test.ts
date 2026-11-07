import assert from "node:assert/strict";
import test from "node:test";
import { claimWorkerEnv } from "./reviewed-chat";

test("claim worker only receives explicitly allowed tracing configuration", () => {
  const result = claimWorkerEnv({ LANGFUSE_TRACING_ENABLED: "true", LANGFUSE_PUBLIC_KEY: "pk-test",
    LANGFUSE_SECRET_KEY: "secret-test", LANGFUSE_BASE_URL: "https://example.test",
    LANGFUSE_CAPTURE_SYNTHETIC_CONTENT: "true", UNRELATED_SECRET: "never-copy", OLLAMA_MODEL: "synthetic" }, "ollama");
  assert.equal(result.LANGFUSE_TRACING_ENABLED, "true");
  assert.equal(result.LANGFUSE_SECRET_KEY, "secret-test");
  assert.equal(result.LANGFUSE_CAPTURE_SYNTHETIC_CONTENT, undefined);
  assert.equal(result.UNRELATED_SECRET, undefined);
  assert.equal(claimWorkerEnv({}, "ollama").LANGFUSE_TRACING_ENABLED, undefined);
});
