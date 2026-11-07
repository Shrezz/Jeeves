import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Link } from 'wouter';
import { type ClaimGuidance, type ClaimReview, type ClaimWorkspace, getGetClaimQueryKey, getGetClaimReviewQueryKey, getListClaimsQueryKey, useRespondToClaimReview } from '@workspace/api-client-react';
import { Btn, Panel, inputCls } from './cw';
import { reviewErrorMessage } from '@/lib/workflow-errors';

export function WorkflowReview({ guide, workspace }: { guide: ClaimGuidance; workspace: ClaimWorkspace }) {
  const flow = guide.workflow!;
  const packet = flow.route === 'file_claim';
  const pending = flow.phase === 'human_review' && !!flow.interruptId;
  const clarify = flow.phase === 'needs_information' && !!flow.interruptId;
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const respond = useRespondToClaimReview();
  const cache = useQueryClient();
  async function decide(action: 'approve' | 'reject' | 'edit' | 'clarify') {
    if (!flow.interruptId || respond.isPending) return;
    setError('');
    try {
      const result = await respond.mutateAsync({ id: guide.claimId, runId: guide.id, data: {
        interruptId: flow.interruptId, version: flow.version, action,
        ...((action === 'edit' || action === 'clarify') ? { feedback: note.trim() } : {}),
      }});
      cache.setQueryData<ClaimWorkspace>(getGetClaimQueryKey(guide.claimId), old => old && ({
        ...old, guidance: old.guidance.map(item => item.id === result.id ? result : item),
      }));
      cache.setQueryData<ClaimReview>(getGetClaimReviewQueryKey(guide.claimId), old => old && ({
        ...old, workspace: { ...old.workspace, guidance: old.workspace.guidance.map(item => item.id === result.id ? result : item) },
      }));
      setNote('');
      void cache.invalidateQueries({queryKey: getListClaimsQueryKey()});
    } catch (err) {
      setError(reviewErrorMessage(err));
    } finally {
      void cache.invalidateQueries({queryKey: getGetClaimQueryKey(guide.claimId)});
      void cache.invalidateQueries({queryKey: getGetClaimReviewQueryKey(guide.claimId)});
    }
  }
  const title = clarify ? 'More information needed' : packet ? 'Homeowners claim packet' : 'Proposed claim update';
  const badge = pending ? 'Awaiting your review' : flow.phase === 'completed' ? (packet ? 'Prepared' : 'Saved') :
    flow.phase === 'rejected' ? 'Declined' : clarify ? 'Clarification requested' : 'Not prepared';
  return <section className="mx-auto max-w-6xl space-y-4 px-5 py-6 sm:px-8" aria-label="Claim review">
    <Panel title={title}>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs font-semibold text-primary"><span className="rounded-full bg-secondary px-3 py-1">{badge}</span>
        {flow.version > 0 && <span>Version {flow.version}</span>}{packet && <span>· Not submitted</span>}</div>
      <p className="text-sm text-muted-foreground">{workspace.policy?.label ?? 'No policy linked'}</p>
      <p className="mt-3 leading-relaxed">{flow.narrative || guide.content}</p>
      {!!flow.fields.length && <dl className="mt-5 grid gap-x-6 gap-y-3 sm:grid-cols-2">
        {flow.fields.map(f => <div key={f.label} className="border-t pt-2"><dt className="text-xs font-semibold text-muted-foreground">{f.label}</dt><dd className="mt-1 text-sm">{f.value}</dd></div>)}</dl>}
      {guide.sources.length > 0 && <details className="mt-5 rounded-xl border p-3 text-sm"><summary className="cursor-pointer font-semibold">Policy evidence · {Array.from(new Set(guide.sources.map(s => s.page))).sort((a,b)=>a-b).map(p=>'p. '+p).join(', ')}</summary>
        {guide.sources.map(s => <blockquote key={s.chunkId} className="mt-3 border-l-2 border-primary/40 pl-3"><strong>Page {s.page} · {s.section}</strong><p className="whitespace-pre-line">{s.excerpt}</p></blockquote>)}</details>}
    </Panel>
    {(pending || clarify) && <Panel title={clarify ? 'Your answer' : 'Your decision'}>
      <p className="mb-3 text-sm leading-6">{clarify ? 'Add the missing detail to continue this request.' : 'The agent reviewer passed this version. Check the facts and policy terms. Approval saves it locally and does not contact an insurer.'}</p>
      <label htmlFor="packet-feedback" className="mb-1 block text-sm font-semibold">{clarify ? 'Missing information' : 'Corrections (if needed)'}</label>
      <textarea id="packet-feedback" maxLength={2500} rows={2} className={inputCls} value={note} onChange={e=>setNote(e.target.value)} />
      <div className="mt-3 flex flex-wrap gap-2">
        {pending && <><Btn disabled={respond.isPending || !!note.trim()} onClick={()=>void decide('approve')}>{packet ? 'Approve local packet' : 'Approve update'}</Btn>
          <Btn variant="outline" disabled={respond.isPending || !note.trim()} onClick={()=>void decide('edit')}>Request changes</Btn>
          <Btn variant="ghost" disabled={respond.isPending} onClick={()=>void decide('reject')}>Decline</Btn></>}
        {clarify && <Btn disabled={respond.isPending || !note.trim()} onClick={()=>void decide('clarify')}>Continue review</Btn>}
      </div>{respond.isPending && <p role="status">Updating this review…</p>}
      {error && <p role="alert" className="mt-2 text-sm text-destructive">{error}</p>}
    </Panel>}
    {packet && flow.phase === 'completed' && <a className="font-semibold text-primary underline" download="prepared-claim-packet.txt"
      href={'data:text/plain;charset=utf-8,' + encodeURIComponent([title, 'Prepared — not submitted', workspace.policy?.label, flow.narrative,
        ...flow.fields.map(f=>f.label+': '+f.value), ...guide.sources.map(s=>'Page '+s.page+' · '+s.section+'\n'+s.excerpt)].join('\n\n'))}>Download approved packet</a>}
    <div><Link className="text-sm font-semibold text-primary underline" href={'/workspace/claim/'+guide.claimId}>Back to claim conversation</Link></div>
  </section>;
}
