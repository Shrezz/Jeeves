import { Link } from 'wouter';
import { ClipboardCheck, FilePenLine } from 'lucide-react';
import type { Claim } from '@workspace/api-client-react';
import { claimStatusLabel } from '@workspace/domain';
import { Btn } from '@/components/cw';
import { DashboardJeevChat } from '@/components/dashboard-jeev-chat';

const sections = [
  {
    id: 'prepare',
    title: 'Prepare Your Claim',
    description: 'Collect your claim details and track preparation before filing with your insurer.',
    empty: 'No claims in preparation yet. Your claim records will appear here.',
    action: 'Prepare a claim',
    href: '/workspace/claim',
    Icon: FilePenLine,
  },
  {
    id: 'submitted',
    title: 'Submitted Claim',
    description: 'Track records submitted in Jeeves, claims you marked as filed with your insurer, and recorded decisions.',
    empty: 'No submitted claims recorded. Submit a reviewed record in Jeeves or record that you filed with your insurer.',
    action: 'View claims',
    href: '/workspace/claim',
    Icon: ClipboardCheck,
  },
] as const;

function isSubmitted(status: Claim['status']) {
  return status === 'submitted_in_claimwise' || status === 'filed_by_user' || status === 'insurer_decision_received';
}

export function DashboardClaimSections({
  claims, loading, error, onRetry,
}: {
  claims: Claim[];
  loading: boolean;
  error: boolean;
  onRetry: () => void;
}) {
  return (
    <div className="space-y-5">
      <DashboardJeevChat />
      {sections.map(({ id, title, description, empty, action, href, Icon }) => {
        const records = claims.filter((claim) => isSubmitted(claim.status) === (id === 'submitted'));
        return (
          <section key={id} aria-labelledby={`${id}-heading`} data-testid={`dashboard-section-${id}`} className="overflow-hidden rounded-2xl border border-card-border bg-card">
            <header className="flex flex-wrap items-start justify-between gap-4 border-b border-card-border p-5">
              <div className="flex min-w-0 flex-1 gap-3">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-secondary text-primary"><Icon className="h-5 w-5" aria-hidden /></span>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 id={`${id}-heading`} className="font-display text-xl">{title}</h2>
                    {!loading && !error && <span aria-label={`${records.length} records`} className="rounded-full bg-muted px-2 py-0.5 text-xs font-semibold text-muted-foreground">{records.length}</span>}
                  </div>
                  <p className="mt-1 text-sm leading-6 text-muted-foreground">{description}</p>
                </div>
              </div>
              <Link href={href} className="inline-flex min-h-10 items-center rounded-lg border border-input px-3 text-sm font-semibold text-primary transition-colors hover:bg-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">{action}</Link>
            </header>
            <div className="p-5">
              {loading ? <div aria-busy="true" aria-label={`Loading ${title}`} className="h-20 animate-pulse rounded-xl bg-muted" />
                : error ? <div role="alert"><p className="text-sm text-muted-foreground">Your claim records couldn’t load.</p><Btn variant="outline" className="mt-3" onClick={onRetry}>Try again</Btn></div>
                : records.length ? (
                  <div className="space-y-3">
                    {records.map((claim) => (
                      <article key={claim.id} data-testid={`card-claim-${claim.id}`} className="rounded-xl border border-card-border p-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <h3 data-testid={`text-claim-title-${claim.id}`} className="min-w-0 break-words font-semibold">{claim.title}</h3>
                          <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${claim.status === 'preparation_requested' || claim.status === 'gathering_evidence' ? 'bg-accent text-accent-foreground' : 'bg-secondary text-secondary-foreground'}`}>{claimStatusLabel(claim.status)}</span>
                        </div>
                        {claim.latestUpdate && <p className="mt-2 line-clamp-2 break-words text-sm text-muted-foreground">{claim.latestUpdate}</p>}
                        <p className="mt-2 text-xs leading-5 text-muted-foreground">Updated {new Date(claim.updatedAt).toLocaleDateString()} · {new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD' }).format(claim.totalExpenses)} recorded expenses</p>
                        <Link href={`/workspace/claim/${encodeURIComponent(claim.id)}`} data-testid={`link-open-claim-${claim.id}`} aria-label={id === 'submitted' ? `Open Claim Details for ${claim.title}` : undefined} className="mt-3 inline-flex min-h-10 items-center rounded-lg border border-input px-3 text-sm font-semibold text-primary hover:bg-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">{id === 'submitted' ? 'Open Claim Details' : 'Open claim'}</Link>
                      </article>
                    ))}
                  </div>
                ) : <p data-testid={`empty-${id}`} className="rounded-xl border border-dashed border-input bg-background p-4 text-sm leading-6 text-muted-foreground">{empty}</p>}
            </div>
          </section>
        );
      })}
    </div>
  );
}
