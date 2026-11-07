import type { Claim, ClaimEvidence, Policy } from '@workspace/api-client-react';
import { UploadCloud, X } from 'lucide-react';
import { EvidenceIcon } from './claim-conversation';
import { PolicyDeclarations } from '@/components/policy-declarations';

const basePath = import.meta.env.BASE_URL.replace(/\/$/, '');
function documentHref(url: string) {
  if (/^https?:\/\//i.test(url)) return url;
  const path = url.startsWith('/') ? url : `/${url}`;
  return basePath && !path.startsWith(`${basePath}/`) && path !== basePath ? `${basePath}${path}` : path;
}
function currency(amount: number) {
  return new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD' }).format(amount);
}
function dateTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Date unavailable' : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}
function fileSize(size: number) {
  return size < 1024 * 1024 ? `${Math.max(1, Math.round(size / 1024))} KB` : `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function ClaimSidebar({
  claim,
  policy,
  evidence,
  attachedIds,
  onRemoveAttachment,
}: {
  claim: Claim;
  policy: Policy | null;
  evidence: ClaimEvidence[];
  attachedIds: string[];
  onRemoveAttachment: (id: string) => void;
}) {
  return (
    <aside className="space-y-4">
      <section className="rounded-2xl border border-card-border bg-card p-5">
        <div className="flex items-center justify-between"><h2 className="font-display text-xl">Evidence</h2><span className="rounded-full bg-secondary px-2.5 py-1 text-xs font-semibold">{evidence.length} {evidence.length === 1 ? 'item' : 'items'}</span></div>
        {evidence.length ? <ul className="mt-4 space-y-2">{evidence.map((item) => <li key={item.id} className="flex items-start gap-3 rounded-xl border border-card-border p-3"><span className="mt-0.5"><EvidenceIcon contentType={item.contentType} /></span><div className="min-w-0 flex-1"><a href={documentHref(item.documentUrl)} download={item.fileName} className="block truncate text-sm font-semibold hover:text-primary">{item.fileName}</a><p className="mt-1 text-xs text-muted-foreground">{item.contentType.startsWith('video/') ? 'Video' : item.contentType.startsWith('image/') ? 'Photo' : 'Document'} · {fileSize(item.size)} · {dateTime(item.createdAt)}</p></div>{attachedIds.includes(item.id) && <button type="button" aria-label={`Remove ${item.fileName} from next entry`} className="rounded p-1 text-muted-foreground hover:text-foreground" onClick={() => onRemoveAttachment(item.id)}><X className="h-4 w-4" aria-hidden /></button>}</li>)}</ul>
          : <div className="mt-4 rounded-xl border border-dashed border-primary/25 bg-[hsl(176_30%_96%)] p-4"><UploadCloud className="h-5 w-5 text-primary" aria-hidden /><p className="mt-2 text-sm font-semibold">No evidence added yet</p><p className="mt-1 text-xs leading-5 text-muted-foreground">Attach a PDF, photo, or video to keep it with this claim.</p></div>}
      </section>
      <section className="rounded-2xl border border-card-border bg-[hsl(176_30%_94%)] p-5"><p className="text-xs font-bold uppercase tracking-[0.12em] text-muted-foreground">Expenses</p><p className="mt-2 font-display text-3xl tabular-nums" data-testid="text-expense-total">{currency(claim.totalExpenses)}</p><p className="mt-1 text-xs text-muted-foreground">Recorded total · amounts add to this running total</p></section>
      <section className="rounded-2xl border border-card-border bg-card p-5">
        <p className="text-xs font-bold uppercase tracking-[0.12em] text-muted-foreground">Selected policy</p>
        {policy ? <><h2 className="mt-2 font-semibold [overflow-wrap:anywhere]">{policy.label}</h2>
          <PolicyDeclarations key={policy.id} policy={policy} compact /></>
          : <p className="mt-2 text-sm leading-5 text-muted-foreground">No saved policy is linked to this claim.</p>}
      </section>
    </aside>
  );
}
