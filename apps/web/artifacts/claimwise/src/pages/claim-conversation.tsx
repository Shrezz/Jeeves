import { Link } from 'wouter';
import { GUIDANCE_LEASE_MS, claimStatusLabel } from "@workspace/domain";
import { FileText, Image, LoaderCircle, Video } from 'lucide-react';
import type { ClaimEvidence, ClaimGuidance, ClaimMessage } from '@workspace/api-client-react';

const basePath = import.meta.env.BASE_URL.replace(/\/$/, '');

function documentHref(url: string) {
  if (/^https?:\/\//i.test(url)) return url;
  const path = url.startsWith('/') ? url : `/${url}`;
  return basePath && !path.startsWith(`${basePath}/`) && path !== basePath ? `${basePath}${path}` : path;
}
function formattedTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Time unavailable' : new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(date);
}
function attachmentIcon(contentType: string) {
  if (contentType.startsWith('video/')) return <Video className="h-4 w-4 shrink-0 text-primary" aria-hidden />;
  if (contentType.startsWith('image/')) return <Image className="h-4 w-4 shrink-0 text-primary" aria-hidden />;
  return <FileText className="h-4 w-4 shrink-0 text-primary" aria-hidden />;
}
function humanBytes(size: number) {
  return size < 1024 * 1024 ? `${Math.max(1, Math.round(size / 1024))} KB` : `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function Attachment({ evidence }: { evidence: ClaimEvidence }) {
  return (
    <li className="flex min-w-0 items-center gap-2 rounded-lg border border-primary-foreground/20 bg-primary-foreground/10 px-2.5 py-2 text-xs">
      {attachmentIcon(evidence.contentType)}
      <span className="min-w-0 flex-1 truncate">{evidence.fileName} <span className="opacity-70">· {humanBytes(evidence.size)}</span></span>
      <a href={documentHref(evidence.documentUrl)} download={evidence.fileName} className="shrink-0 font-semibold underline underline-offset-2 hover:no-underline">Download</a>
    </li>
  );
}

function GuidanceCard({
  messageId,
  guidance,
  active,
  expired,
  requestError,
  onRetry,
}: {
  messageId: string;
  guidance?: ClaimGuidance;
  active: boolean;
  expired: boolean;
  requestError: boolean;
  onRetry: () => void;
}) {
  const pending = active || guidance?.state === 'pending';
  const failed = requestError || guidance?.state === 'error' || (guidance?.state === 'ready' && !guidance.content);
  if (active || (pending && !expired)) {
    return <div role="status" aria-live="polite" className="mt-3 flex items-center gap-2 rounded-xl border border-primary/20 bg-secondary/70 px-4 py-3 text-sm text-secondary-foreground"><LoaderCircle className="h-4 w-4 animate-spin" aria-hidden /> Preparing your answer…</div>;
  }
  if (failed || (guidance?.state === 'pending' && expired)) {
    const stale = guidance?.state === 'pending' && expired;
    return <div role="status" aria-live="polite" className="mt-3 rounded-xl border border-[hsl(38_70%_65%)] bg-accent/60 p-4"><p className="text-sm font-semibold">{stale ? 'Guidance is taking longer than expected.' : 'Your message is saved; guidance is unavailable.'}</p><p className="mt-1 text-xs leading-5 text-muted-foreground">Retry guidance without resending your message or expense.</p><button type="button" data-testid={`button-retry-guidance-${messageId}`} onClick={onRetry} className="mt-3 inline-flex min-h-9 items-center gap-2 rounded-lg border border-input bg-card px-3 text-sm font-semibold hover:border-primary hover:text-primary">Retry guidance</button></div>;
  }
  if (guidance?.state === 'ready' && guidance.content) {
    return <article role="status" aria-live="polite" className="mt-3 rounded-2xl rounded-bl-md border border-[hsl(200_24%_82%)] bg-[hsl(200_35%_96%)] px-4 py-3 text-sm leading-6"><p className="mb-1 text-[11px] font-bold uppercase tracking-wider text-primary">Claimwise AI guidance · {formattedTime(guidance.updatedAt)}</p><div className="space-y-2">{guidance.content.split(/\n+/).filter(Boolean).map((paragraph, i) => <p key={i}>{paragraph}</p>)}</div>
      {guidance.workflow && ['human_review','needs_information','completed','rejected'].includes(guidance.workflow.phase) && <Link
        href={'/workspace/review?claim='+encodeURIComponent(guidance.claimId)+'&run='+encodeURIComponent(guidance.id)}
        className="mt-3 inline-flex rounded-lg bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground">{guidance.workflow.phase === 'needs_information' ? 'Provide missing details' : guidance.workflow.route === 'file_claim' ? 'Review claim packet' : 'Review proposed update'}</Link>}
      {guidance.sources.length > 0 && <details className="mt-3 border-t border-primary/20 pt-2 text-xs leading-5">
        <summary className="cursor-pointer font-semibold text-primary">Policy evidence · {Array.from(new Set(guidance.sources.map(s => s.page))).sort((a, b) => a - b).map(p => 'p. ' + p).join(', ')}</summary>
        <ul className="mt-2 space-y-2">{guidance.sources.map((s, i) => <li key={i} className="border-l-2 border-primary/40 pl-3"><p className="font-semibold">Page {s.page}{s.section && ' · ' + s.section}</p><blockquote>“{s.excerpt}”</blockquote></li>)}</ul>
      </details>}</article>;
  }
  return <div className="mt-3 rounded-xl border border-dashed border-primary/25 bg-[hsl(176_30%_96%)] px-4 py-3"><p className="text-sm font-semibold">Guidance hasn’t started for this message.</p><button type="button" data-testid={`button-get-guidance-${messageId}`} onClick={onRetry} className="mt-2 inline-flex min-h-9 items-center gap-2 rounded-lg bg-primary px-3 text-sm font-semibold text-primary-foreground hover:bg-primary/90">Get guidance</button></div>;
}

export function ClaimConversation({
  messages,
  guidance,
  evidence,
  activeGuidanceId,
  guidanceErrors,
  now,
  onRequestGuidance,
}: {
  messages: ClaimMessage[];
  guidance: ClaimGuidance[];
  evidence: ClaimEvidence[];
  activeGuidanceId: string | null;
  guidanceErrors: Record<string, boolean>;
  now: number;
  onRequestGuidance: (messageId: string) => void;
}) {
  const evidenceById = new Map(evidence.map((item) => [item.id, item]));
  return (
    <ol className="flex-1 space-y-5 p-4 sm:p-5">
      {messages.length === 0 ? (
        <li className="grid min-h-64 place-items-center rounded-xl border border-dashed border-primary/20 bg-[hsl(176_30%_96%)] p-6 text-center">
          <div className="max-w-md">
            <span className="mx-auto grid h-11 w-11 place-items-center rounded-xl bg-card text-primary"><FileText className="h-5 w-5" aria-hidden /></span>
            <h3 className="mt-3 font-display text-xl">Start wherever you are.</h3>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">In your own words, tell us what happened, when you noticed it, and what was damaged. Share what you remember; you can add details as you go.</p>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">Photos or videos can help document the scene. You can add them to your message below.</p>
          </div>
        </li>
      ) : messages.map((item) => {
        const attached = [...new Set([...(item.attachmentIds ?? []), ...evidence.filter((file) => file.messageId === item.id).map((file) => file.id)])]
          .map((id) => evidenceById.get(id)).filter((file): file is ClaimEvidence => !!file);
        const response = guidance.find((reply) => reply.messageId === item.id);
        const pendingMs = response?.state === 'pending' ? Math.max(0, now - new Date(response.updatedAt).getTime()) : 0;
        const expired = response?.state === 'pending' && pendingMs > GUIDANCE_LEASE_MS;
        const isActive = activeGuidanceId === item.id;
        return (
          <li key={item.id} className="flex flex-col items-end">
            <article className="max-w-[94%] rounded-2xl rounded-br-md bg-primary px-4 py-3 text-sm leading-relaxed text-primary-foreground sm:max-w-[82%]">
              <p className="mb-1 text-[11px] font-bold uppercase tracking-wider text-primary-foreground/70">You · {formattedTime(item.createdAt)}</p>
              {item.content && <p className="whitespace-pre-wrap">{item.content}</p>}
              {item.status && <p className="mt-2 rounded-lg bg-primary-foreground/10 px-2.5 py-1.5 text-xs font-semibold">Status recorded: {claimStatusLabel(item.status)}</p>}
              {item.expense !== null && <p className="mt-2 text-xs font-semibold">Expense recorded: {new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD' }).format(item.expense)}</p>}
              {attached.length > 0 && <ul aria-label="Evidence attached to this message" className="mt-3 space-y-2">{attached.map((file) => <Attachment key={file.id} evidence={file} />)}</ul>}
            </article>
            {(item.kind === 'ask' || (item.kind === 'preparation_request' && import.meta.env.VITE_LOCAL_POLICY_SEARCH)) && <div className="w-full max-w-[94%] sm:max-w-[82%]"><GuidanceCard messageId={item.id} guidance={response} active={isActive} expired={!!expired} requestError={!!guidanceErrors[item.id]} onRetry={() => onRequestGuidance(item.id)} /></div>}
          </li>
        );
      })}
    </ol>
  );
}

export function EvidenceIcon({ contentType }: { contentType: string }) {
  return attachmentIcon(contentType);
}
