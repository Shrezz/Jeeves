import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  getGetClaimReviewQueryKey, getGetClaimQueryKey, getListClaimsQueryKey,
  useSaveClaimReviewComments, useSubmitClaimReview,
} from '@workspace/api-client-react';
import type { ClaimReview } from '@workspace/api-client-react';
import { ClipboardCheck } from 'lucide-react';
import { Btn, Field, Notice, Panel, inputCls } from '@/components/cw';

function errorText(error: unknown) {
  const data = (error as { data?: { error?: unknown } } | null)?.data;
  return typeof data?.error === 'string' ? data.error : 'The request could not be confirmed. Your comments are kept here; please retry.';
}

export function ReviewActions({ review, ready, onReload }: {
  review: ClaimReview | undefined; ready: boolean; onReload: () => void;
}) {
  const client = useQueryClient();
  const claimId = review?.workspace.claim.id ?? '';
  const draftKey = ['review-comments-draft', claimId];
  const [draft, setDraft] = useState<string | null>(() => client.getQueryData<string>(draftKey) ?? null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const save = useSaveClaimReviewComments();
  const submit = useSubmitClaimReview();
  const comments = draft ?? review?.comments ?? '';
  const submitted = !!review?.submittedAt;
  const disabled = !ready || !review || busy || submitted;
  const update = (value: string) => {
    setDraft(value); setNotice('');
    client.setQueryData(draftKey, value);
  };
  const persist = async (submission: boolean) => {
    if (disabled || !review || busyRef.current) return;
    busyRef.current = true; setBusy(true); setError(''); setNotice('');
    try {
      const data = { comments, version: review.version };
      const result = submission
        ? await submit.mutateAsync({ id: claimId, data: { ...data, sourceUpdatedAt: review.sourceUpdatedAt } })
        : await save.mutateAsync({ id: claimId, data });
      client.setQueryData(getGetClaimReviewQueryKey(claimId), result);
      client.removeQueries({ queryKey: draftKey, exact: true });
      void client.invalidateQueries({ queryKey: getListClaimsQueryKey() });
      void client.invalidateQueries({ queryKey: getGetClaimQueryKey(claimId) });
      if (mounted.current) {
        setDraft(null);
        setNotice(submission ? 'Submitted in Claimwise. Nothing was sent to your insurer.' : 'Your comments are saved.');
      }
    } catch (err) {
      if (mounted.current) setError(errorText(err));
    } finally {
      busyRef.current = false;
      if (mounted.current) setBusy(false);
    }
  };
  return (
    <>
      <Panel title="Your Comments">
        <Field id="review-comments" label="Your comments" hint={submitted ? 'Comments are part of your saved submission and cannot be changed here.' : 'Add any information you want included. Submit also saves these comments.'}>
          <textarea id="review-comments" data-testid="input-comments" rows={4} maxLength={12000}
            className={`${inputCls} resize-y disabled:opacity-60`} value={comments}
            disabled={!ready || !review || busy} readOnly={submitted}
            onChange={(event) => update(event.target.value)} placeholder="Enter your comments…" />
        </Field>
        {!submitted && <Btn variant="outline" className="mt-3" data-testid="button-save-review-comments" disabled={disabled} onClick={() => void persist(false)}>Save comments</Btn>}
      </Panel>
      {submitted ? (
        <Notice tone="ok" title="Submitted in Claimwise">
          Saved {new Date(review!.submittedAt!).toLocaleString()}. This is a record of your submission within Claimwise, not an insurer filing.
        </Notice>
      ) : (
        <Notice tone="info" title="Submit within Claimwise">
          Submit saves the reviewed information and your comments in Claimwise. It does not send anything to your insurer or confirm coverage.
        </Notice>
      )}
      {error && <div role="alert" className="rounded-xl border border-destructive/25 bg-destructive/5 p-4 text-sm"><p>{error}</p><Btn variant="outline" className="mt-2" disabled={busy} onClick={onReload}>Reload review</Btn></div>}
      {notice && <p role="status" className="text-sm font-medium text-primary">{notice}</p>}
      <div className="space-y-3">
        <div className="flex flex-wrap gap-2">
          <Btn variant="outline" disabled title="Use the claim workspace to add incident details">Edit</Btn>
          <Btn variant="ghost" disabled title="Use the claim workspace to update status">Resolve without filing</Btn>
          <Btn className="ml-auto" data-testid="button-submit-claim" disabled={disabled} onClick={() => void persist(true)}>
            <ClipboardCheck className="h-4 w-4" aria-hidden /> {submit.isPending ? 'Submitting…' : 'Submit Your Claim'}
          </Btn>
        </div>
        {!submitted && <p className="text-xs text-muted-foreground">{ready ? 'Review the information above before submitting. Missing items are noted for your reference.' : 'Submission is available after the review data loads successfully.'}</p>}
      </div>
    </>
  );
}
