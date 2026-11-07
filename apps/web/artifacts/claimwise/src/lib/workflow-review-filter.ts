import type { ClaimGuidance } from '@workspace/api-client-react';

/** Only actionable workflow outcomes belong on the review page. */
export function isWorkflowReview(guide: Pick<ClaimGuidance, 'workflow'>): boolean {
  const flow = guide.workflow;
  if (!flow || !['human_review', 'needs_information', 'completed', 'rejected', 'blocked'].includes(flow.phase)) return false;
  return flow.route !== 'answer_claim' || flow.phase === 'needs_information';
}
