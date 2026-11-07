import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getListPoliciesQueryKey, useRetryPolicyIndex, useSearchPolicy, type Policy } from '@workspace/api-client-react';
import { Btn, inputCls } from './cw';

export function PolicySearch({ policy }: { policy: Policy }) {
  const [question, setQuestion] = useState('');
  const queryClient = useQueryClient();
  const search = useSearchPolicy();
  const retry = useRetryPolicyIndex();
  if (!policy.ingestionStatus) return null;
  const current = retry.data ?? policy;
  return <section aria-label="Search this policy" className="mt-5 space-y-3 rounded-xl border bg-card p-4">
    <h3 className="font-semibold">Search this policy</h3>
    {current.ingestionStatus === 'ready' ? <>
      <p className="text-sm text-secondary-foreground">Indexed · {current.indexedChunks} searchable passages</p>
      <form className="space-y-2" onSubmit={e => { e.preventDefault(); if (question.trim()) search.mutate({ id: policy.id, data: { question: question.trim() } }); }}>
        <label className="text-sm font-medium" htmlFor={'policy-query-' + policy.id}>Find a clause in the original PDF</label>
        <input id={'policy-query-' + policy.id} className={inputCls} value={question} maxLength={800}
          onChange={e => setQuestion(e.target.value)} placeholder="For example: What does it say about window boarding?" />
        <Btn type="submit" disabled={!question.trim() || search.isPending}>{search.isPending ? 'Searching…' : 'Find passages'}</Btn>
      </form>
      {search.isError && <p role="alert">Search is temporarily unavailable. Try again.</p>}
      {search.data && <div aria-live="polite" className="space-y-3">
        {search.data.passages.length === 0 && <p>No passages found.</p>}
        {search.data.passages.map(hit => <article className="border-l-2 border-primary pl-3 text-sm" key={hit.chunkId}>
          <p className="font-semibold">Page {hit.page} · {hit.section}</p>
          <blockquote className="mt-1 whitespace-pre-line text-muted-foreground">{hit.excerpt}</blockquote>
        </article>)}
      </div>}
    </> : <>
      <p className="text-sm" role="status">{current.ingestionStatus === 'failed'
        ? 'Your PDF is saved, but indexing failed. Use a text-based PDF; scanned images need OCR.'
        : current.ingestionStatus === 'processing' ? 'Your PDF is saved. Indexing is in progress or was interrupted.' : 'Your PDF is saved and has not been indexed yet.'}</p>
      <Btn variant="outline" disabled={retry.isPending} onClick={() => retry.mutate({ id: policy.id }, {
        onSuccess: () => { void queryClient.invalidateQueries({ queryKey: getListPoliciesQueryKey() }); },
      })}>{retry.isPending ? 'Indexing…' : 'Retry indexing'}</Btn>
      {retry.isError && <p role="alert">Could not start indexing. Your original is still saved.</p>}
    </>}
  </section>;
}
