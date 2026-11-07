import assert from "node:assert/strict";
import test from "node:test";
import { frontendConfig, localConfig, LOCAL_DATABASE_URL } from "./local-config.mjs";

const keys = { CLERK_PUBLISHABLE_KEY: "pk_test_synthetic", CLERK_SECRET_KEY: "sk_test_synthetic" };

test("local launcher rejects missing, placeholder, or production keys without printing secrets", () => {
  for (const env of [{}, { ...keys, CLERK_SECRET_KEY: "sk_live_private" }, { ...keys, CLERK_PUBLISHABLE_KEY: "pk_test_replace_me" }]) {
    assert.throws(() => localConfig(env), (error) => error.message.includes("development key") && !error.message.includes("private"));
  }
});

test("local startup always selects the isolated database and same-origin proxy", () => {
  const env = localConfig({ ...keys, DATABASE_URL: "postgresql://unrelated-db", NODE_ENV: "production", AI_INTEGRATIONS_OPENAI_API_KEY: "paid-key" });
  assert.equal(env.DATABASE_URL, LOCAL_DATABASE_URL);
  assert.equal(env.NODE_ENV, "development");
  assert.equal(env.VITE_CLERK_PUBLISHABLE_KEY, keys.CLERK_PUBLISHABLE_KEY);
  assert.equal(env.CLERK_AUTHORIZED_PARTIES, "http://localhost:5173");
  assert.equal(env.LOCAL_API_PROXY_TARGET, "http://127.0.0.1:8080");
  assert.equal(env.AI_INTEGRATIONS_OPENAI_API_KEY, "");
  assert.equal(env.DASHBOARD_CHAT_PROVIDER, "ollama");
});

test("the frontend process receives no backend or unrelated public-prefixed secret", () => {
  const env = frontendConfig(localConfig({ ...keys, PATH: "/usr/bin", OPENAI_API_KEY: "secret", VITE_ACCIDENTAL_SECRET: "secret" }));
  assert.equal(env.VITE_CLERK_PUBLISHABLE_KEY, keys.CLERK_PUBLISHABLE_KEY);
  assert.equal(env.PATH, "/usr/bin");
  for (const name of ["CLERK_SECRET_KEY", "DATABASE_URL", "OPENAI_API_KEY", "VITE_ACCIDENTAL_SECRET"]) assert.equal(env[name], undefined);
});

test("Nebius requires an independent reviewer and uses the same pairing on both chat surfaces", () => {
  const nebius = { ...keys, CLAIM_CHAT_PROVIDER: "nebius", NEBIUS_API_KEY: "private",
    NEBIUS_GENERATOR_MODEL: "g", NEBIUS_REVIEWER_MODEL: "r" };
  const config = localConfig(nebius);
  assert.equal(config.DASHBOARD_CHAT_PROVIDER, "nebius");
  assert.equal(config.CLAIM_CHAT_PROVIDER, "nebius");
  assert.equal(frontendConfig(config).NEBIUS_API_KEY, undefined);
  assert.throws(() => localConfig({ ...nebius, NEBIUS_REVIEWER_MODEL: "g" }), /distinct/);
  assert.throws(() => localConfig({ ...nebius, NEBIUS_API_KEY: "" }), /NEBIUS_API_KEY/);
});
