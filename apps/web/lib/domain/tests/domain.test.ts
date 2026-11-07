import assert from "node:assert/strict";
import test from "node:test";

import { clerkUserId, claimStatusLabel, MANUAL_CLAIM_STATUS_VALUES } from "../src/index";
import { SaveClaimMessageBody } from "../../api-zod/src/generated/api";

test("Clerk identity is preserved; UUIDs and emails are not identity substitutes", () => {
  assert.equal(clerkUserId("user_2Example"), "user_2Example");
  for (const value of ["", "demo-user", "test@example.test", "user_", " user_123", "user_123\n"]) {
    assert.throws(() => clerkUserId(value));
  }
});

test("canonical lifecycle values retain friendly UI labels", () => {
  assert.equal(claimStatusLabel("prepared"), "Package prepared");
  assert.equal(claimStatusLabel("filed_by_user"), "Filed by me with insurer");
  assert.equal(claimStatusLabel("Gathering evidence"), "Gathering evidence");
});

test("manual updates cannot claim a generated packet or use repair/run states", () => {
  const body = { clientMessageId: "4384c9f2-ad71-41e2-a151-3fc15672a505", content: "User report", kind: "status_update" };
  for (const status of MANUAL_CLAIM_STATUS_VALUES) {
    assert.equal(SaveClaimMessageBody.safeParse({ ...body, status }).success, true);
  }
  for (const status of ["prepared", "preparation_requested", "repaired", "awaiting_review", "filed_demo"]) {
    assert.equal(SaveClaimMessageBody.safeParse({ ...body, status }).success, false);
  }
});
