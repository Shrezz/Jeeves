import assert from "node:assert/strict";
import test from "node:test";
import { dashboardReply } from "./dashboard-chat";

test("a missing router does not silently send dashboard chat to a different provider", async t => {
  const root = process.env.CLAIM_CHAT_ROOT;
  delete process.env.CLAIM_CHAT_ROOT;
  t.after(() => { if (root !== undefined) process.env.CLAIM_CHAT_ROOT = root; });
  const outbound = t.mock.method(globalThis, "fetch");
  await assert.rejects(dashboardReply("conversation", "owner", null, "What is a deductible?", []), /routing runtime/);
  assert.equal(outbound.mock.callCount(), 0);
});
