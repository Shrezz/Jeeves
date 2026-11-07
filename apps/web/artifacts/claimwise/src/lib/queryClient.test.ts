import assert from 'node:assert/strict';
import test from 'node:test';
import { createAccountQueryClient } from './queryClient';

const key = ['/api/claims'];

test('account caches never share records', () => {
  const a = createAccountQueryClient();
  const b = createAccountQueryClient();
  a.setQueryData(key, [{ title: 'Account A private claim' }]);
  assert.notEqual(a, b);
  assert.equal(b.getQueryData(key), undefined);
  a.clear(); b.clear();
});

test('late old-account mutation results cannot overwrite the current account cache', async () => {
  const a = createAccountQueryClient();
  const b = createAccountQueryClient();
  b.setQueryData(key, [{ title: 'Account B private claim' }]);
  let finish!: (value: { title: string }[]) => void;
  const delayed = new Promise<{ title: string }[]>((resolve) => { finish = resolve; });
  // Mutation callbacks can still run even after query cancellation/cache clear.
  const oldCallback = delayed.then((result) => a.setQueryData(key, result));
  a.clear();
  finish([{ title: 'Late Account A response' }]);
  await oldCallback;
  assert.deepEqual(b.getQueryData(key), [{ title: 'Account B private claim' }]);
  a.clear(); b.clear();
});

test('returning to an account uses a fresh cache rather than reviving old state', () => {
  const firstA = createAccountQueryClient();
  firstA.setQueryData(key, [{ title: 'Old private record' }]);
  const b = createAccountQueryClient();
  const secondA = createAccountQueryClient();
  firstA.setQueryData(key, [{ title: 'Late old-session response' }]);
  assert.equal(b.getQueryData(key), undefined);
  assert.equal(secondA.getQueryData(key), undefined);
  firstA.clear(); b.clear(); secondA.clear();
});
