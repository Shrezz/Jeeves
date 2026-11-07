import { OUT_OF_SCOPE_MESSAGE } from '@workspace/domain';

export function reviewErrorMessage(error: unknown, action?: string): string {
  if (error && typeof error === 'object' && 'status' in error) {
    if (error.status === 400 && 'data' in error && error.data && typeof error.data === 'object' &&
        'error' in error.data && error.data.error === OUT_OF_SCOPE_MESSAGE) return OUT_OF_SCOPE_MESSAGE;
    if (error.status === 409) return 'The claim or review changed. Open the claim conversation to request a fresh draft.';
  }
  if (action === 'edit') return 'The revised packet is not ready. Retry Request changes with the same correction.';
  return 'Your decision could not be confirmed. Check the current review before retrying.';
}
