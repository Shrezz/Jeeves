import { GUIDANCE_LEASE_MS, claimStatusLabel, MANUAL_CLAIM_STATUS_VALUES } from "@workspace/domain";
import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Link } from 'wouter';
import {
  ClaimStatus, getGetClaimQueryKey, getListClaimsQueryKey,
  useCompleteClaimEvidence, useGetClaim, useInitiateClaimEvidence, useRequestClaimGuidance, useSaveClaimMessage,
} from '@workspace/api-client-react';
import type { ClaimMessage, ManualClaimStatus as ClaimStatusType } from '@workspace/api-client-react';
import {
  ArrowLeft, Check, Paperclip, RefreshCw, Send, ShieldCheck,
} from 'lucide-react';
import { ClaimConversation } from './claim-conversation';
import { ClaimSidebar } from './claim-sidebar';

const statuses = MANUAL_CLAIM_STATUS_VALUES;
type Composer = { message: string; expense: string; attachments: string[]; statusComment?: string; nextStatus?: ClaimStatusType; statusForm?: boolean };
const composerByClaim = new Map<string, Composer>();
const messageIds = new Map<string, { signature: string; id: string }>();
let currentOwner: string | null = null;
export function setClaimDraftOwner(owner: string | null) {
  if (owner !== currentOwner) {
    composerByClaim.clear();
    messageIds.clear();
    currentOwner = owner;
  }
}
function storeComposer(key: string, value: Composer) {
  composerByClaim.delete(key);
  composerByClaim.set(key, value);
  if (composerByClaim.size > 20) composerByClaim.delete(composerByClaim.keys().next().value as string);
}
function storeRetry(key: string, value: { signature: string; id: string }) {
  messageIds.delete(key);
  messageIds.set(key, value);
  if (messageIds.size > 20) messageIds.delete(messageIds.keys().next().value as string);
}

function actionClass(variant: 'primary' | 'outline' = 'outline') {
  return `inline-flex min-h-10 items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50 ${variant === 'primary' ? 'bg-primary text-primary-foreground hover:bg-primary/90' : 'border border-input bg-card hover:border-primary hover:text-primary'}`;
}

export function ClaimWorkspacePage({ claimId }: { claimId: string }) {
  const queryClient = useQueryClient();
  const { data: workspace, isLoading, isError, refetch } = useGetClaim(claimId, {
    query: { enabled: !!claimId, queryKey: getGetClaimQueryKey(claimId), staleTime: 10000, refetchOnWindowFocus: true },
  });
  const saveMessage = useSaveClaimMessage();
  const initiateEvidence = useInitiateClaimEvidence();
  const completeEvidence = useCompleteClaimEvidence();
  const requestGuidance = useRequestClaimGuidance();
  const draftKey = `${currentOwner ?? 'signed-out'}:${claimId}`;
  const ownerAtRender = currentOwner;
  const initial = composerByClaim.get(draftKey) ?? { message: '', expense: '', attachments: [] };
  const [message, setMessage] = useState(initial.message);
  const [expense, setExpense] = useState(initial.expense);
  const [attachments, setAttachments] = useState<string[]>(initial.attachments);
  const [saveError, setSaveError] = useState('');
  const [uploadError, setUploadError] = useState('');
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [prepareConfirmed, setPrepareConfirmed] = useState(false);
  const [statusForm, setStatusForm] = useState(initial.statusForm ?? false);
  const [nextStatus, setNextStatus] = useState<ClaimStatusType>(initial.nextStatus ?? ClaimStatus.gathering_evidence);
  const [statusComment, setStatusComment] = useState(initial.statusComment ?? '');
  const [busy, setBusy] = useState(false);
  const [receipt, setReceipt] = useState('');
  const [guidanceBusyId, setGuidanceBusyId] = useState<string | null>(null);
  const [guidanceErrors, setGuidanceErrors] = useState<Record<string, boolean>>({});
  const [now, setNow] = useState(Date.now());
  const busyRef = useRef(false);
  const uploadBusyRef = useRef(false);
  const guidanceRequestRef = useRef<string | null>(null);
  const uploadTicket = useRef<{ signature: string; id: string; uploadURL: string; started: number; uploaded: boolean } | null>(null);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const claimIdRef = useRef(claimId);
  claimIdRef.current = claimId;
  const fileInputRef = useRef<HTMLInputElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const focusedClaimRef = useRef<string | null>(null);
  const refetchRef = useRef(refetch);
  refetchRef.current = refetch;

  useEffect(() => {
    document.title = workspace?.claim.title ? `${workspace.claim.title} — File Your Claim — Claimwise` : 'File Your Claim — Claimwise';
  }, [workspace?.claim.title]);
  useEffect(() => {
    const value = composerByClaim.get(`${currentOwner ?? 'signed-out'}:${claimId}`) ?? { message: '', expense: '', attachments: [] };
    setMessage(value.message); setExpense(value.expense); setAttachments(value.attachments);
    setStatusComment(value.statusComment ?? ''); setNextStatus(value.nextStatus ?? ClaimStatus.gathering_evidence);
    setSaveError(''); setUploadError(''); setPreparing(false); setPrepareConfirmed(false); setStatusForm(value.statusForm ?? false);
  }, [claimId]);
  const pendingGuidance = workspace?.guidance.filter((item) => item.state === 'pending')
    .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())[0];
  useEffect(() => {
    if (!pendingGuidance) return;
    const timer = window.setInterval(() => {
      if (Date.now() - new Date(pendingGuidance.updatedAt).getTime() > GUIDANCE_LEASE_MS) {
        setNow(Date.now());
        window.clearInterval(timer);
        return;
      }
      setNow(Date.now());
      void refetchRef.current();
    }, 2000);
    return () => window.clearInterval(timer);
  }, [pendingGuidance?.id, pendingGuidance?.updatedAt]);
  useEffect(() => {
    if (!workspace || workspace.messages.length || focusedClaimRef.current === claimId) return;
    focusedClaimRef.current = claimId;
    window.requestAnimationFrame(() => composerRef.current?.focus());
  }, [claimId, workspace?.messages.length]);
  const persistComposer = (next: Composer) => storeComposer(draftKey, next);
  const updateMessage = (value: string) => { setMessage(value); persistComposer({ message: value, expense, attachments, statusComment, nextStatus, statusForm }); };
  const updateExpense = (value: string) => { setExpense(value); persistComposer({ message, expense: value, attachments, statusComment, nextStatus, statusForm }); };
  const updateAttachments = (value: string[]) => { setAttachments(value); persistComposer({ message, expense, attachments: value, statusComment, nextStatus, statusForm }); };
  const updateStatusComment = (value: string) => { setStatusComment(value); persistComposer({ message, expense, attachments, statusComment: value, nextStatus, statusForm }); };
  const updateNextStatus = (value: ClaimStatusType) => { setNextStatus(value); persistComposer({ message, expense, attachments, statusComment, nextStatus: value, statusForm }); };
  const updateStatusForm = (value: boolean) => { setStatusForm(value); persistComposer({ message, expense, attachments, statusComment, nextStatus, statusForm: value }); };

  const uploadFile = async (file: File) => {
    if (uploadBusyRef.current || busyRef.current) return;
    const targetId = claimId;
    setUploadError('');
    const extension = file.name.toLowerCase().split('.').pop();
    const allowedTypes = ['application/pdf', 'image/png', 'image/jpeg', 'video/mp4', 'video/webm', 'video/quicktime'];
    const extensionType: Record<string, string> = { pdf: 'application/pdf', png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', mp4: 'video/mp4', webm: 'video/webm', mov: 'video/quicktime' };
    const contentType = allowedTypes.includes(file.type) ? file.type : (!file.type || file.type === 'application/octet-stream' ? extensionType[extension ?? ''] : undefined);
    if (!contentType) {
      setUploadError(extension === 'heic' || extension === 'heif' ? 'HEIC photos are not supported yet. Export or convert them to JPG or PNG.' : 'Choose a PDF, PNG, JPG, MP4, WebM, or MOV file.');
      return;
    }
    const maxBytes = contentType.startsWith('video/') ? 100 * 1024 * 1024 : 20 * 1024 * 1024;
    if (!file.size || file.size > maxBytes) { setUploadError(contentType.startsWith('video/') ? 'Videos must be between 1 byte and 100 MB.' : 'PDFs and photos must be between 1 byte and 20 MB.'); return; }
    uploadBusyRef.current = true;
    setUploadProgress(0); setReceipt('');
    try {
      const signature = JSON.stringify([file.name, file.size, contentType, file.lastModified]);
      if (!uploadTicket.current || uploadTicket.current.signature !== signature || Date.now() - uploadTicket.current.started > 14 * 60 * 1000) {
        const signed = await initiateEvidence.mutateAsync({ id: targetId, data: { fileName: file.name, size: file.size, contentType: contentType as 'application/pdf' | 'image/png' | 'image/jpeg' | 'video/mp4' | 'video/webm' | 'video/quicktime' } });
        uploadTicket.current = { ...signed, signature, started: Date.now(), uploaded: false };
      }
      const ticket = uploadTicket.current;
      if (!ticket.uploaded) await new Promise<void>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('PUT', ticket.uploadURL);
          xhr.timeout = 300000;
          xhr.setRequestHeader('Content-Type', contentType);
        xhr.upload.onprogress = (event) => { if (event.lengthComputable) setUploadProgress(Math.round((event.loaded / event.total) * 100)); };
        xhr.onload = () => xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error('Upload failed'));
        xhr.onerror = () => reject(new Error('Upload failed'));
        xhr.ontimeout = () => reject(new Error('Upload timed out'));
        xhr.onabort = () => reject(new Error('Upload cancelled'));
        xhr.send(file);
      });
      ticket.uploaded = true;
      const evidence = await completeEvidence.mutateAsync({ id: targetId, evidenceId: ticket.id });
      if (currentOwner !== ownerAtRender) return;
      const current = composerByClaim.get(draftKey) ?? { message: '', expense: '', attachments: [] };
      const next = { ...current, attachments: [...new Set([...current.attachments, evidence.id])].slice(0, 10) };
      storeComposer(draftKey, next);
      uploadTicket.current = null;
      if (mounted.current && claimIdRef.current === targetId) { setAttachments(next.attachments); setUploadProgress(null); setReceipt('Evidence saved privately to this claim.'); }
      void queryClient.invalidateQueries({ queryKey: getGetClaimQueryKey(targetId) });
      void queryClient.invalidateQueries({ queryKey: getListClaimsQueryKey() });
    } catch {
      setUploadError('The upload was not confirmed. Check the evidence list, or choose the same file to safely retry.');
      setUploadProgress(null);
      void queryClient.invalidateQueries({ queryKey: getGetClaimQueryKey(targetId) });
    } finally {
      uploadBusyRef.current = false;
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const requestGuidanceFor = async (messageId: string) => {
    if (guidanceRequestRef.current || currentOwner !== ownerAtRender) return;
    guidanceRequestRef.current = messageId;
    setGuidanceBusyId(messageId);
    setGuidanceErrors((current) => ({ ...current, [messageId]: false }));
    try {
      const result = await requestGuidance.mutateAsync({ id: claimId, data: { messageId } });
      if (currentOwner !== ownerAtRender) return;
      queryClient.setQueryData(getGetClaimQueryKey(claimId), (old: typeof workspace) => old
        ? { ...old, guidance: [...old.guidance.filter((item) => item.messageId !== messageId && item.id !== result.id), result] }
        : old);
      if (mounted.current && claimIdRef.current === claimId) {
        setReceipt(result.state === 'ready' ? 'Guidance is ready. Review it for accuracy.' : result.state === 'pending' ? 'Your message is saved. Guidance is processing.' : 'Your message is saved; guidance is unavailable.');
      }
      void queryClient.invalidateQueries({ queryKey: getGetClaimQueryKey(claimId) });
    } catch {
      if (currentOwner === ownerAtRender) {
        setGuidanceErrors((current) => ({ ...current, [messageId]: true }));
        if (mounted.current && claimIdRef.current === claimId) setReceipt('Your message is saved; guidance is unavailable. You can retry guidance below.');
        void refetchRef.current();
      }
    } finally {
      if (guidanceRequestRef.current === messageId) guidanceRequestRef.current = null;
      if (currentOwner === ownerAtRender) setGuidanceBusyId(null);
    }
  };

  const send = async (kind: 'ask' | 'preparation_request' | 'status_update', content: string, status?: ClaimStatusType, withConfirmation = false) => {
    if (busyRef.current || uploadBusyRef.current || !workspace) return;
    if (withConfirmation && !prepareConfirmed) return;
    if (guidanceRequestRef.current || guidanceBusyId || workspace.guidance.some((item) => item.state === 'pending' && now - new Date(item.updatedAt).getTime() < GUIDANCE_LEASE_MS)) {
      setSaveError('Please wait for the current guidance response before sending another update.');
      return;
    }
    const cleanContent = content.trim();
    if (kind === 'ask' && !cleanContent && !expense.trim() && !attachments.length) { setSaveError('Write a message, record an expense, or attach evidence before asking.'); return; }
    const amount = kind !== 'status_update' && expense.trim() ? Number(expense.replace(/[$,]/g, '')) : undefined;
    const entryAttachments = kind === 'status_update' ? [] : attachments;
    if (amount !== undefined && (!Number.isFinite(amount) || amount < 0 || amount > 100000000)) { setSaveError('Enter a valid non-negative expense amount.'); return; }
    const signature = JSON.stringify([claimId, kind, cleanContent, amount ?? null, status ?? null, entryAttachments]);
    let retry = messageIds.get(draftKey);
    if (retry && retry.signature !== signature) {
      busyRef.current = true;
      setBusy(true);
      try {
        const refreshed = await refetch({ throwOnError: true });
        const previousWasRecorded = refreshed.data?.messages.some((entry) => entry.id === retry?.id) ?? false;
        if (previousWasRecorded) setSaveError('Your previous entry was saved. This edited text will be recorded as a separate entry.');
        messageIds.delete(draftKey);
      } catch {
        setSaveError('Before changing a saved entry, Claimwise could not confirm whether the last attempt was recorded. Try again when you’re connected.');
        busyRef.current = false;
        setBusy(false);
        return;
      }
      busyRef.current = false;
      setBusy(false);
      retry = undefined;
    }
    if (!retry || retry.signature !== signature) { retry = { signature, id: crypto.randomUUID() }; storeRetry(draftKey, retry); }
    busyRef.current = true; setBusy(true); setSaveError(''); setReceipt('');
    const sentTo = claimId;
    let savedMessage: ClaimMessage;
    try {
      savedMessage = await saveMessage.mutateAsync({
        id: sentTo,
        data: { clientMessageId: retry.id, content: cleanContent, kind, ...(amount !== undefined ? { expense: amount } : {}), ...(status ? { status } : {}), ...(entryAttachments.length ? { attachmentIds: entryAttachments } : {}) },
      });
    } catch {
      setSaveError('This update was not confirmed. Your text and amount are still here; try again to safely retry.');
      busyRef.current = false; setBusy(false);
      return;
    }
    if (currentOwner !== ownerAtRender) { busyRef.current = false; setBusy(false); return; }
    messageIds.delete(draftKey);
    const savedDraft = kind === 'status_update' ? { message, expense, attachments, statusComment: '', nextStatus, statusForm: false } : { message: '', expense: '', attachments: [], statusComment, nextStatus, statusForm };
    storeComposer(draftKey, savedDraft);
    queryClient.setQueryData(getGetClaimQueryKey(sentTo), (old: typeof workspace) => old
      ? { ...old, messages: [...old.messages.filter((item) => item.id !== savedMessage.id), savedMessage].sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime()) }
      : old);
    if (mounted.current && claimIdRef.current === sentTo) {
      if (kind === 'status_update') { setStatusForm(false); setStatusComment(''); }
      else { setMessage(''); setExpense(''); setAttachments([]); setPreparing(false); setPrepareConfirmed(false); }
      setReceipt(kind === 'status_update' ? 'Status update saved.' : kind === 'preparation_request' ? 'Preparation request saved.' : 'Your message is saved. Requesting guidance…');
    }
    void queryClient.invalidateQueries({ queryKey: getGetClaimQueryKey(sentTo) });
    void queryClient.invalidateQueries({ queryKey: getListClaimsQueryKey() });
    busyRef.current = false; setBusy(false);
    if (kind === 'ask' || (kind === 'preparation_request' && import.meta.env.VITE_LOCAL_POLICY_SEARCH)) void requestGuidanceFor(savedMessage.id);
  };

  if (isLoading) return <LoadingClaim />;
  if (isError || !workspace) return <main className="mx-auto max-w-4xl px-5 py-10"><section role="alert" className="rounded-3xl border border-card-border bg-card p-7"><h1 className="font-display text-3xl">Claim workspace unavailable</h1><p className="mt-2 text-sm text-muted-foreground">We couldn’t load this claim. It may not exist or may no longer be available.</p><div className="mt-5 flex gap-2"><button type="button" className={actionClass()} onClick={() => void refetch()}><RefreshCw className="h-4 w-4" aria-hidden /> Try again</button><Link href="/workspace/claim" className={actionClass()}>Choose another claim</Link></div></section></main>;

  const { claim, policy, messages, evidence, guidance } = workspace;
  const guidancePendingLive = guidance.some((item) => item.state === 'pending' && now - new Date(item.updatedAt).getTime() < GUIDANCE_LEASE_MS);
  const guidanceGate = guidancePendingLive || guidanceBusyId !== null;
  return (
    <main className="mx-auto max-w-7xl">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-card-border bg-card/70 px-5 py-4 sm:px-8">
        <div className="flex min-w-0 items-center gap-3">
          <Link href="/workspace/claim" aria-label="Choose a different claim" className="grid h-9 w-9 shrink-0 place-items-center rounded-lg hover:bg-secondary"><ArrowLeft className="h-4 w-4" aria-hidden /></Link>
          <div className="min-w-0"><p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">File Your Claim · {claimStatusLabel(claim.status)}</p><h1 className="truncate font-display text-2xl" data-testid="text-claim-title">{claim.title}</h1></div>
        </div>
        <span className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-secondary px-3 py-1.5 text-xs font-semibold text-secondary-foreground"><ShieldCheck className="h-3.5 w-3.5" aria-hidden /> Private workspace</span>
      </header>
      <div className="grid gap-5 p-4 sm:p-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <section aria-label="Conversation" className="flex min-h-[610px] flex-col overflow-hidden rounded-2xl border border-card-border bg-card">
          <div className="border-b border-card-border px-5 py-4">
            <div className="flex items-center justify-between gap-3"><div><h2 className="font-semibold">Claim conversation</h2><p className="text-xs text-muted-foreground">A private record of your notes and evidence.</p></div><span className="rounded-full bg-muted px-2.5 py-1 text-xs font-medium">{messages.length} {messages.length === 1 ? 'entry' : 'entries'}</span></div>
            <p className="mt-3 rounded-lg border border-primary/15 bg-secondary/60 px-3 py-2 text-xs leading-5 text-muted-foreground">AI guidance can be incomplete—review it for accuracy. It is not legal advice or an insurer’s coverage decision. {import.meta.env.VITE_LOCAL_POLICY_SEARCH ? 'Answers can cite the indexed policy linked to this claim. Other attachments are used by name only.' : 'Guidance uses your conversation and attachment details only.'}</p>
          </div>
          <ClaimConversation messages={messages} guidance={guidance} evidence={evidence} activeGuidanceId={guidanceBusyId} guidanceErrors={guidanceErrors} now={now} onRequestGuidance={(messageId) => void requestGuidanceFor(messageId)} />
          <form className="space-y-3 border-t border-card-border bg-background/70 p-4 sm:p-5" onSubmit={(event) => { event.preventDefault(); void send('ask', message); }}>
            <fieldset disabled={busy} className="space-y-3">
            <div><label htmlFor="claim-message" className="mb-1.5 block text-sm font-semibold">Message</label><textarea ref={composerRef} id="claim-message" rows={3} maxLength={12000} value={message} onChange={(event) => updateMessage(event.target.value)} placeholder="Tell us what happened, in your own words" data-testid="input-message" className="w-full resize-y rounded-xl border border-input bg-card px-3 py-2.5 text-sm leading-6 focus:border-primary focus:outline-none" /></div>
            <div className="flex flex-wrap items-end gap-3">
              <div><label htmlFor="claim-expense" className="mb-1.5 block text-sm font-semibold">Expense amount <span className="font-normal text-muted-foreground">(optional)</span></label><input id="claim-expense" inputMode="decimal" value={expense} onChange={(event) => updateExpense(event.target.value)} placeholder="$0.00" data-testid="input-expense" className="min-h-10 w-36 rounded-lg border border-input bg-card px-3 font-mono text-sm focus:border-primary focus:outline-none" /></div>
              <label className={`${actionClass()} cursor-pointer ${uploadProgress !== null ? 'pointer-events-none opacity-50' : ''}`}><Paperclip className="h-4 w-4" aria-hidden />Add photo, video, or document<input ref={fileInputRef} type="file" accept=".pdf,.png,.jpg,.jpeg,.mp4,.webm,.mov,application/pdf,image/png,image/jpeg,video/mp4,video/webm,video/quicktime" className="sr-only" disabled={uploadProgress !== null} data-testid="input-attach" onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadFile(file); }} /></label>
              <div className="ml-auto flex flex-wrap gap-2">
                <button type="button" className={actionClass()} data-testid="button-update-status" onClick={() => { updateStatusForm(!statusForm); setPreparing(false); }}><RefreshCw className="h-4 w-4" aria-hidden /> Update status</button>
                <button type="button" className={actionClass()} data-testid="button-prepare-claim" onClick={() => { setPreparing((value) => !value); updateStatusForm(false); }}><Check className="h-4 w-4" aria-hidden /> Prepare claim</button>
                <button type="submit" className={actionClass('primary')} data-testid="button-ask" disabled={busy || uploadProgress !== null || guidanceGate}><Send className="h-4 w-4" aria-hidden /> Ask</button>
              </div>
            </div>
            {uploadProgress !== null && <div role="status" aria-live="polite" className="rounded-lg bg-secondary px-3 py-2 text-sm"><div className="flex justify-between"><span>Uploading evidence</span><span>{uploadProgress}%</span></div><div className="mt-2 h-1.5 overflow-hidden rounded-full bg-card"><div className="h-full bg-primary transition-[width]" style={{ width: `${uploadProgress}%` }} /></div></div>}
            {uploadError && <p role="alert" className="text-sm text-destructive">{uploadError}</p>}
            {attachments.length > 0 && <p className="text-xs text-muted-foreground">{attachments.length} uploaded {attachments.length === 1 ? 'file is' : 'files are'} attached to your next saved entry.</p>}
            {saveError && <p role="alert" className="rounded-lg border border-destructive/25 bg-destructive/5 px-3 py-2 text-sm text-destructive">{saveError}</p>}
            </fieldset>
            <p role="status" aria-live="polite" className="text-sm font-medium text-primary">{receipt || (busy ? 'Saving your entry…' : '')}</p>
            <p className="text-xs leading-5 text-muted-foreground">Ask saves your message and recorded expense, then requests AI guidance. {import.meta.env.VITE_LOCAL_POLICY_SEARCH ? 'Ask to prepare a claim when you want a packet for review. Nothing is submitted to an insurer.' : 'Nothing is submitted to your insurer.'} Claim attachments are saved as evidence; their contents are not analyzed.</p>
          </form>
          {preparing && <div className="border-t border-primary/20 bg-secondary/50 p-4 sm:px-5"><p className="font-semibold">Request claim preparation?</p><p className="mt-1 text-sm leading-5 text-muted-foreground">{import.meta.env.VITE_LOCAL_POLICY_SEARCH ? 'Prepare a draft from your saved incident and policy evidence for human review.' : 'This saves a request for future processing.'} Nothing will be sent to your insurer.</p><label className="mt-3 flex items-start gap-2 text-sm"><input type="checkbox" checked={prepareConfirmed} onChange={(event) => setPrepareConfirmed(event.target.checked)} className="mt-1 accent-[hsl(178_64%_27%)]" /><span>I understand this request does not file a claim with my insurer.</span></label><div className="mt-3 flex flex-wrap gap-2"><button type="button" className={actionClass('primary')} disabled={!prepareConfirmed || busy} onClick={() => void send('preparation_request', message, undefined, true)}><Check className="h-4 w-4" aria-hidden /> Confirm request</button><button type="button" className={actionClass()} onClick={() => { setPreparing(false); setPrepareConfirmed(false); }}>Cancel</button></div></div>}
          {statusForm && <form className="border-t border-primary/20 bg-secondary/50 p-4 sm:px-5" onSubmit={(event) => { event.preventDefault(); void send('status_update', statusComment, nextStatus); }}><h3 className="font-semibold">Record a status update</h3><label htmlFor="claim-status" className="mb-1.5 mt-3 block text-sm font-semibold">Status</label><select id="claim-status" value={nextStatus} onChange={(event) => updateNextStatus(event.target.value as ClaimStatusType)} className="min-h-10 w-full rounded-lg border border-input bg-card px-3 text-sm">{statuses.map((status) => <option key={status} value={status}>{claimStatusLabel(status)}</option>)}</select><label htmlFor="status-comment" className="mb-1.5 mt-3 block text-sm font-semibold">Comment <span className="font-normal text-muted-foreground">(optional)</span></label><textarea id="status-comment" rows={2} maxLength={12000} value={statusComment} onChange={(event) => updateStatusComment(event.target.value)} placeholder="Add a note about this update" className="w-full rounded-lg border border-input bg-card px-3 py-2 text-sm" /><p className="mt-2 text-xs leading-5 text-muted-foreground">This records the status you select; it is not an insurer coverage decision.</p><div className="mt-3 flex gap-2"><button type="submit" className={actionClass('primary')} disabled={busy}><Check className="h-4 w-4" aria-hidden /> Save status</button><button type="button" className={actionClass()} onClick={() => updateStatusForm(false)}>Cancel</button></div></form>}
        </section>
        <ClaimSidebar claim={claim} policy={policy} evidence={evidence} attachedIds={attachments} onRemoveAttachment={(id) => updateAttachments(attachments.filter((attachedId) => attachedId !== id))} />
      </div>
    </main>
  );
}

function LoadingClaim() {
  return <main className="mx-auto max-w-7xl p-5 sm:p-8" aria-busy="true" aria-label="Loading claim workspace"><div className="h-16 animate-pulse rounded-2xl bg-muted" /><div className="mt-5 grid gap-5 lg:grid-cols-[1fr_320px]"><div className="h-[580px] animate-pulse rounded-2xl bg-card" /><div className="space-y-4"><div className="h-64 animate-pulse rounded-2xl bg-card" /><div className="h-32 animate-pulse rounded-2xl bg-card" /></div></div></main>;
}
