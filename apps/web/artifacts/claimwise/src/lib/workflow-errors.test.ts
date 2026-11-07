import assert from 'node:assert/strict';
import { test } from 'node:test';
import { OUT_OF_SCOPE_MESSAGE } from '@workspace/domain';
import { reviewErrorMessage } from './workflow-errors';

test('review shows the scope guard response and keeps conflict errors distinct', () => {
  assert.equal(reviewErrorMessage({ status: 400, data: { error: OUT_OF_SCOPE_MESSAGE } }), OUT_OF_SCOPE_MESSAGE);
  assert.match(reviewErrorMessage({ status: 409 }), /review changed/);
  assert.match(reviewErrorMessage({ status: 400, data: { error: 'unexpected' } }), /could not be confirmed/);
});
