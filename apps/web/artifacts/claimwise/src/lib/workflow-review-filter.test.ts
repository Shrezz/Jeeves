import assert from 'node:assert/strict';
import { test } from 'node:test';
import { isWorkflowReview } from './workflow-review-filter';

test('review list excludes ordinary answers and scope-guard replies', () => {
  const flow = { version: 0, fields: [] };
  assert.equal(isWorkflowReview({ workflow: { ...flow, route: 'clarify', phase: 'answer_ready' } }), false);
  assert.equal(isWorkflowReview({ workflow: { ...flow, route: 'answer_claim', phase: 'answer_ready' } }), false);
  assert.equal(isWorkflowReview({ workflow: { ...flow, route: 'file_claim', phase: 'human_review' } }), true);
  assert.equal(isWorkflowReview({ workflow: { ...flow, route: 'clarify', phase: 'needs_information' } }), true);
  assert.equal(isWorkflowReview({ workflow: { ...flow, route: 'file_claim', phase: 'blocked' } }), true);
});
