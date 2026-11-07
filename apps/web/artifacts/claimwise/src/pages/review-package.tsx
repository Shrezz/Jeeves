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
  getGetClaimQueryKey,
  getListClaimsQueryKey,
  useGetClaim,
  useListClaims,
} from '@workspace/api-client-react';
import type { Claim, ClaimWorkspace } from '@workspace/api-client-react';
import { Btn, Field, Notice, Panel, Status, cx, inputCls } from '@/components/cw';

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
  if (status === 'Preparation requested' || status === 'Package prepared' || status === 'Filed by me with insurer') return 'pending';
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
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Review package</p>
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
  workspace,
  claimLoading,
  claimError,
  onRetryClaim,
}: {
  workspace: ClaimWorkspace | undefined;
  claimLoading: boolean;
  claimError: boolean;
  onRetryClaim: () => void;
}) {
  const claim = workspace?.claim;
  const incidentMessages = (workspace?.messages ?? [])
    .filter((message) => message.kind === 'ask' && message.content.trim().length > 0)
    .slice()
    .sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  const expenseMessages = (workspace?.messages ?? [])
    .filter((message) => message.expense !== null && message.expense !== undefined);
  const notes = (workspace?.messages ?? [])
    .filter((message) => message.kind === 'preparation_request')
    .filter((message) => {
      const content = message.content.trim().replace(/[.!?]+$/, '').trim().toLowerCase();
      return content.length > 0 && content !== 'preparation requested';
    })
    .slice()
    .sort((a, b) => a.createdAt.localeCompare(b.createdAt));

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
          <EmptyPanel>No clauses are stored for review. Policy labels or general guidance are not treated as cited policy language.</EmptyPanel>
        </Panel>
      </div>

      <div className="space-y-6">
        <Panel title="Reviewer result">
          <EmptyPanel>No reviewer assessment is stored. This page shows saved claim information only; no package has been generated or reviewed.</EmptyPanel>
        </Panel>
        <Panel title="Missing fields">
          <EmptyPanel>No missing-field assessment is stored. Claimwise does not infer missing items on this page.</EmptyPanel>
        </Panel>
        <Panel title="Your comments">
          {claimError ? (
            <EmptyPanel>Saved preparation notes could not be loaded. Retry the claim request to view them.</EmptyPanel>
          ) : notes.length ? (
            <div className="space-y-3">
              {notes.map((note) => (
                <div key={note.id} className="rounded-xl border border-card-border bg-background/60 p-3" data-testid={`text-preparation-note-${note.id}`}>
                  <p className="mb-1 font-mono text-[11px] text-muted-foreground">{dateLabel(note.createdAt) ?? 'Date not recorded'} · Saved preparation note</p>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">{note.content}</p>
                </div>
              ))}
            </div>
          ) : (
            <Field id="review-comments" label="Notes for the package" hint="Read-only. Comment editing and saving are not available here.">
              <textarea
                id="review-comments"
                rows={3}
                className={cx(inputCls, 'resize-none opacity-80')}
                value=""
                readOnly
                placeholder="No saved preparation notes."
                aria-readonly="true"
                data-testid="input-comments"
              />
            </Field>
          )}
        </Panel>
        <Notice tone="info" title="Saved information, not a prepared package">
          This view brings together details already saved to your claim. It does not generate a review, decide coverage, or submit anything to your insurer.
        </Notice>
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <Btn variant="outline" disabled aria-disabled="true" title="Editing is not available in the review view" data-testid="button-edit-review">Edit</Btn>
            <Btn variant="ghost" disabled aria-disabled="true" title="This status action is not available here" data-testid="button-resolve">Resolve without filing</Btn>
            <Btn className="ml-auto" disabled aria-disabled="true" title="Package generation is not available" data-testid="button-approve"><ClipboardCheck className="h-4 w-4" aria-hidden /> Approve &amp; prepare</Btn>
          </div>
          <p className="text-xs leading-relaxed text-muted-foreground">These actions are unavailable because Claimwise does not yet support package generation or status changes from this page.</p>
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
  const claimQuery = useGetClaim(claimId, {
    query: {
      enabled: !!claimId,
      queryKey: getGetClaimQueryKey(claimId),
      staleTime: 10000,
      refetchOnWindowFocus: true,
    },
  });
  const workspace = claimQuery.data?.claim.id === claimId ? claimQuery.data : undefined;
  const isClaimLoading = !!claimId && (claimQuery.isLoading || (!workspace && claimQuery.isFetching));
  const listLoading = claimsQuery.isLoading;
  const listFailed = claimsQuery.isError && (!claimsQuery.data || claimsQuery.data.length === 0);

  useEffect(() => {
    document.title = 'Review Package — Claimwise';
  }, []);

  return (
    <div>
      <ReviewHeader claim={selectedClaim ?? null} />
      <div className="mx-auto max-w-6xl space-y-4 px-5 pt-5 sm:px-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-primary">Claim preparation</p>
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">A read-only view of information saved to your account. No package has been prepared.</p>
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
            <Panel title="Your comments"><Field id="empty-review-comments" label="Notes for the package" hint="Read-only. Comment editing and saving are not available here."><textarea id="empty-review-comments" rows={3} className={cx(inputCls, 'resize-none opacity-80')} readOnly value="" placeholder="No saved preparation notes." aria-readonly="true" /></Field></Panel>
            <Notice tone="info" title="Saved information, not a prepared package">Claimwise has no saved claims in this account yet. This view does not generate a package or submit anything to your insurer.</Notice>
            <div className="space-y-3"><div className="flex flex-wrap gap-2"><Btn variant="outline" disabled aria-disabled="true">Edit</Btn><Btn variant="ghost" disabled aria-disabled="true">Resolve without filing</Btn><Btn className="ml-auto" disabled aria-disabled="true"><ClipboardCheck className="h-4 w-4" aria-hidden /> Approve &amp; prepare</Btn></div><p className="text-xs text-muted-foreground">Actions become available only when supported by the product.</p><Link href="/workspace/claim" data-testid="link-start-claim" className="inline-flex min-h-10 items-center gap-2 rounded-lg px-2 text-sm font-semibold text-primary underline-offset-4 hover:underline"><FileText className="h-4 w-4" aria-hidden /> Start a claim</Link></div>
          </div>
        </div>
      ) : (
        <ReviewPanels
          key={claimId}
          workspace={workspace}
          claimLoading={isClaimLoading}
          claimError={claimQuery.isError}
          onRetryClaim={() => void claimQuery.refetch()}
        />
      )}
    </div>
  );
}
