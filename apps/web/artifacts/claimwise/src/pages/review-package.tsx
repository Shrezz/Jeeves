import { useEffect, useState } from 'react';
import { Link } from 'wouter';
import {
  ArrowLeft,
  Check,
  ClipboardCheck,
  FileText,
  Pencil,
  Quote,
  RefreshCw,
} from 'lucide-react';
import {
  getGetClaimReviewQueryKey,
  getListClaimsQueryKey,
  useGetClaimReview,
  useListClaims,
} from '@workspace/api-client-react';
import type { Claim, ClaimReview } from '@workspace/api-client-react';
import { Btn, Field, Notice, Panel, Status, cx, inputCls } from '@/components/cw';
import { ReviewActions } from '@/components/review-actions';

function money(value: number) {
  return new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD' }).format(value);
}

function dateLabel(value: string | null | undefined) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(date);
}

function claimTone(status: string): 'ok' | 'pending' | 'neutral' {
  if (status === 'Resolved without filing' || status === 'Insurer decision received') return 'ok';
  if (status === 'Preparation requested' || status === 'Package prepared' || status === 'Submitted in Claimwise' || status === 'Filed by me with insurer') return 'pending';
  return 'neutral';
}

function ReviewHeader({
  claim,
}: {
  claim: Claim | null;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b bg-card/60 px-5 py-4 sm:px-10">
      <div className="flex min-w-0 items-center gap-3">
        <Link
          href="/workspace/dashboard"
          aria-label="Back to dashboard"
          data-testid="link-review-back"
          className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
        </Link>
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Review Claim</p>
          <h1 className="truncate font-display text-2xl" data-testid="text-claim-title">
            {claim?.title ?? 'Your saved claim information'}
          </h1>
        </div>
      </div>
      {claim && <Status tone={claimTone(claim.status)} testId="status-current">Status: {claim.status}</Status>}
    </div>
  );
}

function LoadingCopy({ className = '' }: { className?: string }) {
  return <div className={cx('h-4 animate-pulse rounded bg-muted', className)} aria-hidden />;
}

function ReviewLoadingPanels() {
  return (
    <div className="grid gap-6 p-5 sm:px-10 lg:grid-cols-[1.4fr_1fr]" aria-label="Loading saved claim information" aria-busy="true">
      <div className="space-y-6">
        <Panel title="Incident summary">
          <LoadingCopy className="w-4/5" />
          <LoadingCopy className="mt-3 w-3/5" />
          <LoadingCopy className="mt-8 w-full" />
          <LoadingCopy className="mt-3 w-full" />
        </Panel>
        <Panel title="Cited clauses">
          <LoadingCopy className="w-2/3" />
          <LoadingCopy className="mt-3 w-5/6" />
        </Panel>
      </div>
      <div className="space-y-6">
        <Panel title="Reviewer result"><LoadingCopy className="w-4/5" /></Panel>
        <Panel title="Missing fields"><LoadingCopy className="w-3/5" /></Panel>
        <Panel title="Your comments"><LoadingCopy className="w-full" /></Panel>
      </div>
    </div>
  );
}

function EmptyPanel({ children }: { children: string }) {
  return (
    <div className="rounded-xl border border-dashed border-border bg-background/60 px-4 py-5 text-sm leading-relaxed text-muted-foreground">
      {children}
    </div>
  );
}

function ReviewPanels({
  review,
  claimLoading,
  claimError,
  reviewReady,
  onRetryClaim,
}: {
  review: ClaimReview | undefined;
  claimLoading: boolean;
  claimError: boolean;
  reviewReady: boolean;
  onRetryClaim: () => void;
}) {
  const workspace = review?.workspace;
  const claim = workspace?.claim;
  const incidentMessages = review?.incidentSummary ?? [];
  const expenseMessages = review?.expenses ?? [];

  if (claimLoading) return <ReviewLoadingPanels />;

  return (
    <div className="grid gap-6 p-5 sm:px-10 lg:grid-cols-[1.4fr_1fr]">
      <div className="space-y-6">
        <Panel
          title="Incident summary"
          action={
            <Btn variant="ghost" className="px-2 py-1 text-xs" disabled aria-disabled="true" title="Editing saved claim details is not available here">
              <Pencil className="h-3.5 w-3.5" aria-hidden /> Edit
            </Btn>
          }
        >
          {claimError ? (
            <div role="alert" className="space-y-3">
              <p className="text-sm text-destructive">Saved claim information could not be loaded.</p>
              <Btn variant="outline" onClick={onRetryClaim} data-testid="button-retry-claim"><RefreshCw className="h-4 w-4" aria-hidden /> Try again</Btn>
            </div>
          ) : !claim ? (
            <EmptyPanel>There is no saved incident information for this claim yet. Choose a claim in the workspace to add details.</EmptyPanel>
          ) : incidentMessages.length ? (
            <div className="space-y-3">
              {incidentMessages.map((message) => (
                <article key={message.id} className="rounded-xl border border-card-border bg-background/60 p-4" data-testid={`text-incident-${message.id}`}>
                  <p className="mb-2 font-mono text-[11px] text-muted-foreground">{dateLabel(message.createdAt) ?? 'Date not recorded'}</p>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.content}</p>
                </article>
              ))}
            </div>
          ) : (
            <EmptyPanel>No incident description has been saved yet.</EmptyPanel>
          )}

          <div className="mt-5 border-t border-dashed pt-4">
            <h3 className="text-xs font-bold uppercase tracking-[0.12em] text-muted-foreground">Recorded expenses</h3>
            {claimError ? (
              <div className="mt-3"><LoadingCopy className="w-2/3" /></div>
            ) : claim && expenseMessages.length ? (
              <table className="mt-2 w-full text-sm">
                <caption className="sr-only">Expenses recorded in this claim</caption>
                <tbody>
                  {expenseMessages.map((message) => (
                    <tr key={message.id} className="border-b border-dashed" data-testid={`row-expense-${message.id}`}>
                      <td className="py-2 pr-4">
                        <span className="block">{message.content.trim() || 'Expense recorded'}</span>
                        <span className="font-mono text-[11px] text-muted-foreground">{dateLabel(message.createdAt) ?? 'Date not recorded'}</span>
                      </td>
                      <td className="py-2 text-right font-mono">{money(message.expense ?? 0)}</td>
                    </tr>
                  ))}
                  <tr>
                    <th className="pt-3 text-left">Claim expense total</th>
                    <td className="pt-3 text-right font-mono font-bold" data-testid="text-expense-total">{money(claim.totalExpenses)}</td>
                  </tr>
                </tbody>
              </table>
            ) : claim ? (
              <div className="mt-2">
                <EmptyPanel>No expense entries have been saved.</EmptyPanel>
                <p className="mt-3 flex justify-between gap-4 border-t border-dashed pt-3 text-sm">
                  <span className="font-semibold">Claim expense total</span>
                  <span className="font-mono" data-testid="text-expense-total">{money(claim.totalExpenses)}</span>
                </p>
              </div>
            ) : (
              <EmptyPanel>Expense details are unavailable until claim information loads.</EmptyPanel>
            )}
          </div>
        </Panel>

        <Panel title={<span className="flex items-center gap-2"><Quote className="h-3.5 w-3.5" aria-hidden /> Cited clauses</span>}>
          {review?.citedClauses.length && !claimError ? <ul className="list-disc space-y-2 pl-5 text-sm">{review.citedClauses.map((clause, i) => <li key={i}>{clause}</li>)}</ul> : <EmptyPanel>No cited policy language is available. Policy wording has not been analyzed.</EmptyPanel>}
        </Panel>
      </div>

      <div className="space-y-6">
        <Panel title="Reviewer result">
          {review && !claimError ? <p className="text-sm leading-6" data-testid="text-reviewer-result">{review.reviewerResult}</p> : <EmptyPanel>Review information is unavailable until the request succeeds.</EmptyPanel>}
        </Panel>
        <Panel title="Missing fields">
          {review && !claimError ? (review.missingFields.length ? <ul className="list-disc space-y-2 pl-5 text-sm" data-testid="list-missing-fields">{review.missingFields.map((field) => <li key={field}>{field}</li>)}</ul> : <p className="text-sm text-muted-foreground">No basic information gaps found. Insurer-specific requirements have not been assessed.</p>) : <EmptyPanel>Missing-field checks are unavailable until the request succeeds.</EmptyPanel>}
        </Panel>
        <ReviewActions key={claim?.id ?? 'unavailable'} review={review} ready={reviewReady} onReload={onRetryClaim} />
        <div className="space-y-3">
          {claim && (
            <Link
              href={`/workspace/claim/${encodeURIComponent(claim.id)}`}
              className="inline-flex min-h-10 items-center gap-2 rounded-lg px-2 text-sm font-semibold text-primary underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
              data-testid="link-open-claim"
            >
              <FileText className="h-4 w-4" aria-hidden /> Open claim workspace
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ReviewPackagePage() {
  const [selectedClaimId, setSelectedClaimId] = useState('');
  const claimsQuery = useListClaims({
    query: {
      queryKey: getListClaimsQueryKey(),
      staleTime: 15000,
      refetchOnWindowFocus: true,
    },
  });
  const claims = claimsQuery.data ?? [];
  const selectedClaim = claims.find((claim) => claim.id === selectedClaimId) ?? claims[0];
  const claimId = selectedClaim?.id ?? '';
  const claimQuery = useGetClaimReview(claimId, {
    query: {
      enabled: !!claimId,
      queryKey: getGetClaimReviewQueryKey(claimId),
      staleTime: 0,
      refetchOnWindowFocus: true,
    },
  });
  const review = claimQuery.data?.workspace.claim.id === claimId ? claimQuery.data : undefined;
  const isClaimLoading = !!claimId && (claimQuery.isLoading || (!review && claimQuery.isFetching));
  const listLoading = claimsQuery.isLoading;
  const listFailed = claimsQuery.isError && (!claimsQuery.data || claimsQuery.data.length === 0);

  useEffect(() => {
    document.title = 'Review Claim — Claimwise';
  }, []);

  return (
    <div>
      <ReviewHeader claim={selectedClaim ?? null} />
      <div className="mx-auto max-w-6xl space-y-4 px-5 pt-5 sm:px-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-primary">Claim preparation</p>
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">Review your saved information, add comments, and submit the record within Claimwise.</p>
          </div>
          {claims.length > 0 && (
            <label className="flex w-full flex-col gap-1.5 text-xs font-semibold text-muted-foreground sm:w-auto">
              <span>Claim</span>
              <select
                aria-label="Select a saved claim"
                className={cx(inputCls, 'min-h-10 w-full sm:min-w-64')}
                value={claimId}
                onChange={(event) => setSelectedClaimId(event.target.value)}
                data-testid="select-review-claim"
              >
                {claims.map((claim) => <option key={claim.id} value={claim.id}>{claim.title}</option>)}
              </select>
            </label>
          )}
        </div>
        {claimsQuery.isError && claimsQuery.data && (
          <Notice tone="error" title="Could not refresh your claim list">
            Showing the account-owned claims already loaded. <button type="button" onClick={() => void claimsQuery.refetch()} className="font-semibold underline underline-offset-2" data-testid="button-retry-claims">Retry</button>
          </Notice>
        )}
        {listFailed && (
          <Notice tone="error" title="Your saved claims could not be loaded">
            We could not check whether you have claims yet. <button type="button" onClick={() => void claimsQuery.refetch()} className="font-semibold underline underline-offset-2" data-testid="button-retry-claims">Try again</button>
          </Notice>
        )}
      </div>
      {listLoading ? (
        <ReviewLoadingPanels />
      ) : listFailed ? (
        <div className="grid gap-6 p-5 sm:px-10 lg:grid-cols-[1.4fr_1fr]">
          <div className="space-y-6"><Panel title="Incident summary"><EmptyPanel>Claim information will appear here after your saved claims load.</EmptyPanel></Panel><Panel title="Cited clauses"><EmptyPanel>No review clauses are available.</EmptyPanel></Panel></div>
          <div className="space-y-6"><Panel title="Reviewer result"><EmptyPanel>No reviewer assessment is available.</EmptyPanel></Panel><Panel title="Missing fields"><EmptyPanel>No missing-field assessment is available.</EmptyPanel></Panel><Panel title="Your comments"><EmptyPanel>Saved preparation notes are unavailable until claims load.</EmptyPanel></Panel></div>
        </div>
      ) : claims.length === 0 ? (
        <div className="grid gap-6 p-5 sm:px-10 lg:grid-cols-[1.4fr_1fr]">
          <div className="space-y-6">
            <Panel title="Incident summary" action={<Btn variant="ghost" className="px-2 py-1 text-xs" disabled aria-disabled="true"><Pencil className="h-3.5 w-3.5" aria-hidden /> Edit</Btn>}>
              <EmptyPanel>No saved claims yet. Once you start a claim, its saved incident details will appear here.</EmptyPanel>
              <div className="mt-5 border-t border-dashed pt-4"><h3 className="mb-3 text-xs font-bold uppercase tracking-[0.12em] text-muted-foreground">Recorded expenses</h3><EmptyPanel>No saved expense entries.</EmptyPanel></div>
            </Panel>
            <Panel title={<span className="flex items-center gap-2"><Quote className="h-3.5 w-3.5" aria-hidden /> Cited clauses</span>}><EmptyPanel>No clauses are stored for review.</EmptyPanel></Panel>
          </div>
          <div className="space-y-6">
            <Panel title="Reviewer result"><EmptyPanel>No reviewer assessment is stored.</EmptyPanel></Panel>
            <Panel title="Missing fields"><EmptyPanel>No missing-field assessment is stored.</EmptyPanel></Panel>
            <Panel title="Your Comments"><Field id="empty-review-comments" label="Your comments" hint="Choose a saved claim before adding comments."><textarea id="empty-review-comments" rows={3} className={cx(inputCls, 'resize-none opacity-80')} disabled value="" placeholder="No claim selected." /></Field></Panel>
            <Notice tone="info" title="Saved information, not a prepared package">Claimwise has no saved claims in this account yet. This view does not generate a package or submit anything to your insurer.</Notice>
            <div className="space-y-3"><div className="flex flex-wrap gap-2"><Btn variant="outline" disabled aria-disabled="true">Edit</Btn><Btn variant="ghost" disabled aria-disabled="true">Resolve without filing</Btn><Btn className="ml-auto" disabled data-testid="button-submit-claim"><ClipboardCheck className="h-4 w-4" aria-hidden /> Submit Your Claim</Btn></div><p className="text-xs text-muted-foreground">Submission is available after a saved claim’s review data loads successfully.</p><Link href="/workspace/claim" data-testid="link-start-claim" className="inline-flex min-h-10 items-center gap-2 rounded-lg px-2 text-sm font-semibold text-primary underline-offset-4 hover:underline"><FileText className="h-4 w-4" aria-hidden /> Start a claim</Link></div>
          </div>
        </div>
      ) : (
        <ReviewPanels
          key={claimId}
          review={review}
          claimLoading={isClaimLoading}
          claimError={claimQuery.isError}
          reviewReady={!!review && claimQuery.isSuccess && !claimQuery.isFetching}
          onRetryClaim={() => void claimQuery.refetch()}
        />
      )}
    </div>
  );
}
