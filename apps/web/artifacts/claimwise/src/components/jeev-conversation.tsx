import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  getGetJeevConversationQueryKey, getListJeevConversationsQueryKey,
  getJeevConversation, useGetJeevConversation, useSendJeevMessage, useListPolicies,
} from '@workspace/api-client-react';
import type { JeevConversationDetail, JeevMessageInput } from '@workspace/api-client-react';
import { GUIDANCE_LEASE_MS } from '@workspace/domain';
import { DashboardClaimHandoff } from './dashboard-claim-handoff';
import { PolicyEvidence } from './policy-evidence';
import { Send } from 'lucide-react';
import { Link } from 'wouter';
import { Btn } from '@/components/cw';

export function JeevConversationWindow({
  conversationId, saved, onClose,
}: { conversationId: string; saved: boolean; onClose: () => void }) {
  const client = useQueryClient();
  const draftKey = ['jeev-conversation-draft', conversationId];
  const initial = client.getQueryData<{ text: string; request: JeevMessageInput | null }>(draftKey);
  const [text, setText] = useState(initial?.text ?? '');
  const request = useRef<JeevMessageInput | null>(initial?.request ?? null);
  const [hasSaved, setHasSaved] = useState(saved);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const mounted = useRef(true);
  const input = useRef<HTMLTextAreaElement>(null);
  const [now, setNow] = useState(Date.now());
  const detail = useGetJeevConversation(conversationId, {
    query: { enabled: hasSaved, staleTime: 10000, refetchOnWindowFocus: true },
  });
  const mutation = useSendJeevMessage();
  const entries = detail.data?.messages ?? [];
  const policies = useListPolicies();
  const indexed = (policies.data ?? []).filter(p => p.ingestionStatus === 'ready');
  const [choice, setChoice] = useState<string | undefined>(initial?.request?.policyId ?? undefined);
  const last = entries.at(-1);
  const selected = choice ?? (last && !last.policyId ? 'general' : last?.policyId && indexed.some(p => p.id === last.policyId) ? last.policyId
    : indexed.length === 1 ? indexed[0].id : indexed.length ? '' : 'general');
  const pending = entries.find((entry) => entry.replyState === 'pending');
  const refetch = useRef(detail.refetch);
  refetch.current = detail.refetch;
  useEffect(() => {
    mounted.current = true;
    input.current?.focus();
    return () => { mounted.current = false; };
  }, []);
  useEffect(() => {
    if (!pending) return;
    const timer = window.setInterval(() => {
      setNow(Date.now());
      if (Date.now() - new Date(pending.updatedAt).getTime() >= GUIDANCE_LEASE_MS) window.clearInterval(timer);
      else void refetch.current();
    }, 2000);
    return () => window.clearInterval(timer);
  }, [pending?.id, pending?.updatedAt]);
  const pendingLive = entries.some((entry) => entry.replyState === 'pending' && now - new Date(entry.updatedAt).getTime() < GUIDANCE_LEASE_MS);
  const updateText = (value: string) => {
    setText(value);
    client.setQueryData(draftKey, { text: value, request: request.current });
  };
  const send = async (content: string, retryId?: string) => {
    if (busyRef.current || pendingLive) return;
    const clean = content.trim();
    if (!clean) { setError('Write a message for Jeeves before sending.'); return; }
    const policyId = retryId ? entries.find(entry => entry.id === retryId)?.policyId ?? null : selected === 'general' ? null : selected;
    if (!retryId && !selected) { setError('Choose a policy or General questions before sending.'); return; }
    const payload = retryId ? { messageId: retryId, content: clean, policyId }
      : request.current?.content === clean && request.current.policyId === policyId ? request.current : { messageId: crypto.randomUUID(), content: clean, policyId };
    if (!retryId) {
      request.current = payload;
      client.setQueryData(draftKey, { text, request: payload });
    }
    busyRef.current = true;
    setBusy(true); setError('');
    try {
      const result = await mutation.mutateAsync({ id: conversationId, data: payload });
      client.setQueryData<JeevConversationDetail>(getGetJeevConversationQueryKey(conversationId), (old) => ({
        conversation: old?.conversation ?? { id: conversationId, title: clean.slice(0, 100), updatedAt: result.updatedAt },
        messages: [...(old?.messages ?? []).filter((entry) => entry.id !== result.id), result]
          .sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime()),
      }));
      if (!retryId) {
        client.removeQueries({ queryKey: draftKey, exact: true });
      }
      void client.invalidateQueries({ queryKey: getGetJeevConversationQueryKey(conversationId) });
      void client.invalidateQueries({ queryKey: getListJeevConversationsQueryKey() });
      if (!mounted.current) return;
      setHasSaved(true);
      if (!retryId) { setText(''); request.current = null; }
    } catch {
      if (!mounted.current) return;
      setError('The reply could not be confirmed. Your text is kept here. Try again to safely retry.');
      // A lost response can follow a successful save. Recover its history without
      // creating another conversation or user message.
      try {
        const recovered = await getJeevConversation(conversationId);
        if (mounted.current) {
          client.setQueryData(getGetJeevConversationQueryKey(conversationId), recovered);
          setHasSaved(true);
          void client.invalidateQueries({ queryKey: getListJeevConversationsQueryKey() });
        }
      } catch { /* Keep the draft and stable message ID for the next retry. */ }
    } finally {
      busyRef.current = false;
      if (mounted.current) { setBusy(false); input.current?.focus(); }
    }
  };
  return (
    <div id="dashboard-jeev-chat" data-testid="dashboard-jeev-chat" className="min-w-0 overflow-hidden rounded-xl border border-primary/25 bg-background">
      <div className="flex items-center justify-between gap-3 border-b border-card-border px-4 py-3">
        <h3 className="font-semibold">Your conversation with Jeeves</h3>
        <Btn variant="ghost" onClick={onClose} data-testid="button-close-dashboard-chat">Close chat</Btn>
      </div>
      <div className="space-y-2 border-b border-card-border px-4 py-3 text-sm">
        <label htmlFor="jeev-policy" className="block font-semibold">Policy for this chat</label>
        <select id="jeev-policy" value={selected} disabled={busy || policies.isLoading || policies.isError}
          onChange={event => setChoice(event.target.value)} className="w-full rounded-lg border border-input bg-card px-3 py-2">
          <option value="" disabled>Choose which policy to check…</option>
          {indexed.map(policy => <option key={policy.id} value={policy.id}>{policy.label}</option>)}
          <option value="general">General questions · no policy</option>
        </select>
        {policies.isError ? <button type="button" className="text-primary underline" onClick={() => void policies.refetch()}>Retry loading policies</button>
          : <p className="text-xs text-muted-foreground">{indexed.length ? 'Select an indexed policy for a short answer with supporting passages.' : 'For answers about your coverage, upload a policy and wait for indexing.'} <Link href="/workspace/upload" className="text-primary underline">Upload a policy</Link></p>}
      </div>
      {detail.isLoading ? <p role="status" className="p-4 text-sm">Loading conversation…</p>
        : detail.isError ? <div role="alert" className="p-4"><p>We couldn’t load this conversation.</p><Btn variant="outline" className="mt-2" onClick={() => void detail.refetch()}>Try again</Btn></div>
        : (
          <ol aria-label="Conversation messages" className="max-h-[480px] space-y-4 overflow-y-auto p-4">
            {!entries.length && <li className="rounded-xl bg-secondary/50 p-4 text-sm leading-6">What would you like to talk about? Ask Jeeves a question or describe what’s on your mind.</li>}
            {entries.map((entry) => (
              <li key={entry.id} className="space-y-3">
                <div className="ml-6 rounded-xl bg-primary p-4 text-sm text-primary-foreground"><p className="mb-1 text-xs font-semibold">You</p><p className="whitespace-pre-wrap break-words">{entry.content}</p></div>
                {entry.replyState === 'ready' && entry.reply
                  ? <div role="status" className="mr-6 rounded-xl border border-primary/15 bg-secondary/50 p-4 text-sm leading-6"><p className="mb-1 text-xs font-semibold text-primary">Jeeves · AI guidance</p><p className="whitespace-pre-wrap break-words">{entry.reply}</p>
                    <PolicyEvidence sources={entry.sources} label={policies.data?.find(p => p.id === entry.policyId)?.label} />
                    {(entry.route === 'file_claim' || entry.route === 'save_claim_status') && <DashboardClaimHandoff entry={entry} history={entries} />}
                  </div>
                  : entry.replyState === 'pending' && now - new Date(entry.updatedAt).getTime() < GUIDANCE_LEASE_MS
                    ? <p role="status" className="text-sm text-muted-foreground">Jeeves is thinking…</p>
                    : <div className="rounded-xl bg-accent/50 p-3 text-sm"><p>Your message is saved, but Jeeves couldn’t reply.</p><Btn variant="outline" className="mt-2" disabled={busy || pendingLive} onClick={() => void send(entry.content, entry.id)}>Retry reply</Btn></div>}
              </li>
            ))}
          </ol>
        )}
      <form className="space-y-3 border-t border-card-border p-4" onSubmit={(event) => { event.preventDefault(); void send(text); }}>
        <label htmlFor="jeev-message" className="block text-sm font-semibold">Message Jeeves</label>
        <textarea id="jeev-message" ref={input} data-testid="input-jeev-message" rows={3} maxLength={12000} value={text} onChange={(event) => updateText(event.target.value)} disabled={busy} className="w-full resize-y rounded-xl border border-input bg-card px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-ring" placeholder="Ask a question or share what’s on your mind…" />
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p role="status" aria-live="polite" className="text-xs text-muted-foreground">{busy ? 'Jeeves is checking your request…' : pendingLive ? 'Waiting for a reply from Jeeves…' : 'Messages are saved privately, separate from claims.'}</p>
          <Btn type="submit" data-testid="button-send-jeev" disabled={busy || pendingLive || !text.trim() || detail.isError || detail.isLoading || policies.isLoading || policies.isError || !selected}><Send className="h-4 w-4" aria-hidden /> Send to Jeeves</Btn>
        </div>
      </form>
    </div>
  );
}
