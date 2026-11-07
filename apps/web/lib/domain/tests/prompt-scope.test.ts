import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { includePromptInHistory, OUT_OF_SCOPE_MESSAGE, promptInScope } from "../src/prompt-scope";

const cases: { text: string; followup?: boolean; allowed: boolean }[] = JSON.parse(
  readFileSync(new URL("../../../../../evals/datasets/prompt_scope_cases.json", import.meta.url), "utf8"),
);
for (const example of cases) {
  test(`scope: ${example.text} (followup=${!!example.followup})`, () => {
    assert.equal(promptInScope(example.text, { followup: example.followup }), example.allowed);
  });
}
test("blocked messages are omitted from future model history", () => {
  assert.equal(includePromptInHistory("How's the weather?", undefined), false);
  assert.equal(includePromptInHistory("yes", OUT_OF_SCOPE_MESSAGE), false);
  assert.equal(includePromptInHistory("yes", "Thanks for clarifying."), true);
});
