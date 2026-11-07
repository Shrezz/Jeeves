import { useRef, useState } from 'react';
import { useLocation } from 'wouter';
import { useQueryClient } from '@tanstack/react-query';
import {
  createClaim, saveClaimMessage, requestClaimGuidance, useListClaims,
  getGetClaimQueryKey, getListClaimsQueryKey, type JeevMessage,
} from '@workspace/api-client-react';
import { Btn } from '@/components/cw';

/** Only an explicit target selection and click may take a chat request into a claim. */
export function DashboardClaimHandoff({ entry, history }: { entry: JeevMessage; history: JeevMessage[] }) {
  const filing = entry.route === 'file_claim';
  const claims = useListClaims();
  const [, go] = useLocation();
  const client = useQueryClient();
  const [target, setTarget] = useState('');
  const [working, setWorking] = useState(false);
  const lock = useRef(false);
  const [error, setError] = useState('');
  const options = (claims.data ?? []).filter(c => !entry.policyId || c.policyId === entry.policyId);
  async function proceed() {
    if (!target || lock.current) return;
    if (!filing) { go('/workspace/claim/' + target + '?edit=status', {state: {statusNote: entry.content}}); return; }
    lock.current = true; setWorking(true); setError('');
    try {
      // The saved chat turn provides stable IDs on double-click, retry or reopening.
      const turns = history.slice(0, history.findIndex(e => e.id === entry.id) + 1).filter(e => e.policyId === entry.policyId).slice(-5);
      const notes = turns.map(e => e.content.slice(0, 1800)).join('\n');
      const id = target === 'new' ? (await createClaim({id: entry.id, title: (turns[0]?.content || 'New claim').slice(0, 100), policyId: entry.policyId})).id : target;
      await saveClaimMessage(id, {clientMessageId: entry.id, kind: 'preparation_request', content: notes});
      void client.invalidateQueries({queryKey: getListClaimsQueryKey()});
      // The request is saved before navigation. The workspace can resume it if generation fails.
      void requestClaimGuidance(id, {messageId: entry.id}).catch(() => {}).finally(() => {
        void client.invalidateQueries({queryKey: getGetClaimQueryKey(id)});
        void client.invalidateQueries({queryKey: getListClaimsQueryKey()});
      });
      go('/workspace/claim/' + id);
    } catch { setError('Couldn’t open this request. Retry with the same claim, or check your saved claims.'); }
    finally { lock.current = false; setWorking(false); }
  }
  return <div className="mt-3 space-y-2 border-t border-primary/20 pt-3">
    <label className="block text-xs font-semibold">Claim for this request
      <select className="mt-1 block w-full rounded-lg border border-input bg-card px-2 py-2 text-sm" value={target} disabled={working || claims.isLoading || claims.isError} onChange={e => setTarget(e.target.value)}>
        <option value="">Choose a claim…</option>{filing && <option value="new">Start a new draft</option>}
        {options.map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
      </select>
    </label>
    {claims.isError && <button onClick={() => void claims.refetch()}>Retry loading claims</button>}
    {!filing && !claims.isLoading && !claims.isError && !options.length && <p>No saved claims match this policy yet.</p>}
    {error && <p role="alert">{error}</p>}
    <Btn variant="outline" disabled={!target || working} onClick={() => void proceed()}>{working ? 'Opening…' : filing ? 'Prepare packet for review' : 'Open status editor'}</Btn>
  </div>;
}
