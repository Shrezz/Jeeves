import { useEffect, useMemo, useState } from 'react';
import { getListClaimsQueryKey, getListPoliciesQueryKey, useListClaims, useListPolicies } from '@workspace/api-client-react';
import type { Policy } from '@workspace/api-client-react';
import { ArrowDownToLine, FileText, FolderOpen, LockKeyhole, UploadCloud } from 'lucide-react';
import { Btn, Panel } from '@/components/cw';
import { DashboardClaimSections } from '@/components/dashboard-claim-sections';
import type { Go } from '@/pages/screens-a';

const basePath = import.meta.env.BASE_URL.replace(/\/$/, '');

function documentHref(url: string) {
  if (/^https?:\/\//i.test(url)) return url;
  const path = url.startsWith('/') ? url : `/${url}`;
  return basePath && !path.startsWith(`${basePath}/`) && path !== basePath ? `${basePath}${path}` : path;
}

function formatDate(date: string) {
  const parsed = new Date(date);
  return Number.isNaN(parsed.getTime())
    ? 'Date unavailable'
    : new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(parsed);
}

function formatBytes(bytes: number) {
  return bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatCurrency(amount: number) {
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  }).format(amount);
}

function PolicyFileLink({ policy }: { policy: Policy }) {
  return (
    <a
      data-testid={`link-download-policy-${policy.id}`}
      href={documentHref(policy.documentUrl)}
      download={policy.fileName}
      className="inline-flex min-h-10 shrink-0 items-center justify-center gap-2 rounded-lg border border-input bg-background px-3 text-sm font-semibold text-foreground transition-colors hover:border-primary hover:text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
    >
      <ArrowDownToLine className="h-4 w-4" aria-hidden />
      Download
    </a>
  );
}

function PolicySummary({
  policies,
  loading,
  error,
  selected,
  onSelect,
  onUpload,
  onRetry,
}: {
  policies: Policy[];
  loading: boolean;
  error: boolean;
  selected?: Policy;
  onSelect: (id: string) => void;
  onUpload: () => void;
  onRetry: () => void;
}) {
  return (
    <Panel title="Policy summary" className="p-5 sm:p-6">
      {loading ? (
        <div aria-busy="true" aria-label="Loading your policy summary" className="space-y-4">
          <div className="h-7 w-2/3 animate-pulse rounded bg-muted" />
          <div className="h-16 animate-pulse rounded-xl bg-muted" />
          <div className="h-24 animate-pulse rounded-xl bg-muted" />
        </div>
      ) : error ? (
        <div role="alert" className="rounded-xl border border-destructive/25 bg-destructive/5 p-4">
          <p className="font-semibold">Policy summary unavailable</p>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">Your saved policy records couldn’t be loaded. No policy details are shown until they’re available.</p>
          <Btn variant="outline" className="mt-4" data-testid="button-retry-policy-summary" onClick={onRetry}>Try again</Btn>
        </div>
      ) : policies.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-[hsl(178_25%_68%)] bg-[hsl(176_30%_94%)] p-5">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-card text-primary"><FolderOpen className="h-5 w-5" aria-hidden /></span>
          <h3 className="mt-4 font-display text-xl">No policy saved yet</h3>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">Upload a homeowner policy PDF to keep its original and the details you entered here.</p>
          <Btn data-testid="button-upload-policy-empty-summary" className="mt-5" onClick={onUpload}><UploadCloud className="h-4 w-4" aria-hidden /> Upload Policy</Btn>
        </div>
      ) : selected ? (
        <div>
          {policies.length > 1 && (
            <div className="mb-4">
              <label htmlFor="policy-summary-select" className="mb-1.5 block text-xs font-semibold uppercase tracking-[0.1em] text-muted-foreground">Select a saved policy</label>
              <select
                id="policy-summary-select"
                data-testid="select-policy-summary"
                value={selected.id}
                onChange={(event) => onSelect(event.target.value)}
                className="min-h-11 w-full rounded-lg border border-input bg-background px-3 text-sm font-medium text-foreground focus:border-primary focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
              >
                {policies.map((policy) => <option key={policy.id} value={policy.id}>{policy.label}</option>)}
              </select>
            </div>
          )}
          <div data-testid={`panel-policy-summary-${selected.id}`} className="rounded-2xl border border-card-border bg-background/65 p-4">
            <div className="flex items-start gap-3">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-secondary text-primary"><FileText className="h-5 w-5" aria-hidden /></span>
              <div className="min-w-0 flex-1">
                <h3 data-testid={`text-policy-label-${selected.id}`} className="break-words font-display text-xl leading-snug">{selected.label}</h3>
                <span data-testid={`status-policy-saved-${selected.id}`} className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-secondary px-2.5 py-1 text-xs font-semibold text-secondary-foreground">
                  <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden />
                  {selected.status === 'saved' ? 'Saved' : selected.status}
                </span>
              </div>
            </div>
            <dl className="mt-5 divide-y divide-dashed divide-border text-sm">
              <div className="flex items-start justify-between gap-4 py-3 first:pt-0">
                <dt className="text-muted-foreground">Deductible</dt>
                <dd data-testid={`text-policy-deductible-${selected.id}`} className="text-right font-semibold tabular-nums">{selected.deductible !== null ? formatCurrency(selected.deductible) : 'Not provided'}</dd>
              </div>
              <div className="py-3">
                <dt className="text-muted-foreground">Original file</dt>
                <dd data-testid={`text-policy-file-${selected.id}`} className="mt-1 break-all font-medium">{selected.fileName}</dd>
              </div>
              <div className="flex items-start justify-between gap-4 py-3 last:pb-0">
                <dt className="text-muted-foreground">Uploaded</dt>
                <dd data-testid={`text-policy-date-${selected.id}`} className="text-right font-medium">{formatDate(selected.createdAt)}</dd>
              </div>
            </dl>
            <p className="mt-4 flex items-start gap-2 rounded-lg bg-muted/70 px-3 py-2.5 text-xs leading-5 text-muted-foreground">
              <LockKeyhole className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" aria-hidden />
              Coverage details have not been extracted from this document.
            </p>
            <div className="mt-4">
              <PolicyFileLink policy={selected} />
            </div>
          </div>
          <button type="button" data-testid="button-upload-another-policy" onClick={onUpload} className="mt-4 inline-flex min-h-10 items-center gap-2 rounded-lg px-2 text-sm font-semibold text-primary transition-colors hover:bg-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
            <UploadCloud className="h-4 w-4" aria-hidden /> Upload another policy
          </button>
        </div>
      ) : null}
    </Panel>
  );
}

export default function DashboardScreen({ go }: { go: Go }) {
  useEffect(() => {
    document.title = 'Dashboard — Claimwise';
  }, []);

  const { data, isLoading, isError, refetch } = useListPolicies({
    query: {
      queryKey: getListPoliciesQueryKey(),
      staleTime: 30_000,
      refetchOnWindowFocus: true,
    },
  });
  const claimsQuery = useListClaims({
    query: { queryKey: getListClaimsQueryKey(), staleTime: 15000, refetchOnWindowFocus: true },
  });
  const policies = useMemo(
    () => [...(data ?? [])].sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()),
    [data],
  );
  const [selectedId, setSelectedId] = useState<string>();
  const selectedPolicy = policies.find((policy) => policy.id === selectedId) ?? policies[0];
  const hasUploadedPolicy = policies.some((policy) => policy.status === 'saved');
  const retry = () => { void refetch(); };

  return (
    <div className="mx-auto max-w-6xl space-y-8 px-5 py-8 sm:px-8 sm:py-12">
      <header className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="inline-flex rounded-full border border-[hsl(178_28%_76%)] bg-secondary px-3 py-1 text-xs font-semibold tracking-[0.04em] text-secondary-foreground">Your private homeowner workspace</p>
          <h1 data-testid="text-dashboard-title" className="mt-3 font-display text-4xl sm:text-5xl">Dashboard</h1>
          <p className="mt-2 max-w-xl leading-6 text-muted-foreground">Your policy documents and claim preparation, kept in one dependable place.</p>
        </div>
        <div className="self-start sm:self-auto">
          <Btn
            data-testid="button-add-policy"
            disabled={hasUploadedPolicy}
            aria-describedby={hasUploadedPolicy ? 'policy-upload-complete' : undefined}
            onClick={() => go('upload')}
            className="min-h-11 disabled:bg-muted disabled:text-muted-foreground disabled:shadow-none disabled:opacity-100"
          >
            <UploadCloud className="h-4 w-4" aria-hidden /> Upload Policy
          </Btn>
          {hasUploadedPolicy && (
            <p id="policy-upload-complete" className="mt-2 text-xs text-muted-foreground">Policy successfully uploaded</p>
          )}
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <DashboardClaimSections
          claims={claimsQuery.data ?? []}
          loading={claimsQuery.isLoading}
          error={claimsQuery.isError}
          onRetry={() => { void claimsQuery.refetch(); }}
        />

        <aside className="space-y-4">
          <PolicySummary
            policies={policies}
            loading={isLoading}
            error={isError}
            selected={selectedPolicy}
            onSelect={setSelectedId}
            onUpload={() => go('upload')}
            onRetry={retry}
          />
          <div className="rounded-2xl border border-[hsl(200_30%_80%)] bg-[hsl(200_40%_96%)] p-4 sm:p-5">
            <p className="font-semibold">Your records vs. insurer decisions</p>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">Claim notes, evidence, expenses, and status updates help you organize a loss. AI guidance is not legal advice or a coverage decision; only your insurer decides coverage or payment.</p>
          </div>
        </aside>
      </div>
    </div>
  );
}
