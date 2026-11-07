import { claimStatusLabel } from "@workspace/domain";
import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'wouter';
import { useQueryClient } from '@tanstack/react-query';
import { getListClaimsQueryKey, getListPoliciesQueryKey, useCreateClaim, useListClaims, useListPolicies } from '@workspace/api-client-react';
import { ArrowLeft, ChevronRight, FileText, LoaderCircle, ShieldCheck } from 'lucide-react';

function actionClass() {
  return 'inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-input bg-card px-3 py-2 text-sm font-semibold transition-colors hover:border-primary hover:text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50';
}
function money(value: number) {
  return new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD' }).format(value);
}

export default function ClaimChooserPage() {
  const [, setLocation] = useLocation();
  const queryClient = useQueryClient();
  const { data: claims, isLoading, isError, refetch } = useListClaims({
    query: { queryKey: getListClaimsQueryKey(), staleTime: 15000, refetchOnWindowFocus: true },
  });
  const policiesQuery = useListPolicies({ query: { queryKey: getListPoliciesQueryKey(), staleTime: 30000 } });
  const createClaim = useCreateClaim();
  const [title, setTitle] = useState('New claim');
  const [policyId, setPolicyId] = useState('');
  const [error, setError] = useState('');
  const createBusy = useRef(false);
  const active = useRef(true);
  useEffect(() => {
    active.current = true;
    return () => { active.current = false; };
  }, []);
  const createRequest = useRef<{ signature: string; id: string } | null>(null);
  useEffect(() => { document.title = 'File Your Claim — Claimwise'; }, []);
  const create = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const name = title.trim() || 'New claim';
    if (createBusy.current) return;
    setError('');
    const signature = JSON.stringify([name, policyId || null]);
    if (!createRequest.current || createRequest.current.signature !== signature) createRequest.current = { signature, id: crypto.randomUUID() };
    createBusy.current = true;
    try {
      const claim = await createClaim.mutateAsync({ data: { id: createRequest.current.id, title: name, ...(policyId ? { policyId } : {}) } });
      if (!active.current) return;
      void queryClient.invalidateQueries({ queryKey: getListClaimsQueryKey() });
      setLocation(`/workspace/claim/${encodeURIComponent(claim.id)}`);
    } catch {
      if (!active.current) return;
      setError('Your claim could not be saved. Your title is still here; try again.');
    } finally { createBusy.current = false; }
  };
  return (
    <main className="mx-auto max-w-6xl space-y-8 px-5 py-8 sm:px-8 sm:py-12">
      <header className="flex flex-wrap items-end justify-between gap-5"><div><p className="inline-flex rounded-full border border-primary/20 bg-secondary px-3 py-1 text-xs font-semibold text-secondary-foreground">Private homeowner workspace</p><h1 className="mt-3 font-display text-4xl sm:text-5xl">File Your Claim</h1><p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">Start with a free-form conversation about your loss. You can add details, photos, and videos as you go.</p></div><Link href="/workspace/dashboard" className="inline-flex min-h-10 items-center gap-2 rounded-lg px-3 text-sm font-semibold text-primary hover:bg-secondary"><ArrowLeft className="h-4 w-4" aria-hidden /> Dashboard</Link></header>
      <div className="grid gap-7 lg:grid-cols-[minmax(0,1fr)_minmax(320px,.88fr)]">
        <section className="rounded-3xl border border-card-border bg-card p-5 shadow-[0_1px_3px_hsl(192_30%_12%/0.04)] sm:p-7"><p className="text-xs font-bold uppercase tracking-[0.13em] text-primary">A new claim record</p><h2 className="mt-2 font-display text-2xl">Begin with a conversation.</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">Create a draft and tell us what happened in your own words. Nothing is submitted to your insurer.</p>
          <form className="mt-6 space-y-5" onSubmit={(event) => void create(event)}><div><label htmlFor="claim-title" className="mb-1.5 block text-sm font-semibold">Claim title <span className="font-normal text-muted-foreground">(optional)</span></label><input id="claim-title" data-testid="input-claim-title" maxLength={160} value={title} onChange={(event) => setTitle(event.target.value)} placeholder="New claim" className="min-h-11 w-full rounded-lg border border-input bg-background px-3 text-sm focus:border-primary focus:outline-none" /><p className="mt-1.5 text-xs text-muted-foreground">Start with “New claim” to use your first message as the title, or enter a title now.</p></div>
            <div><label htmlFor="claim-policy" className="mb-1.5 block text-sm font-semibold">Saved policy <span className="font-normal text-muted-foreground">(optional)</span></label><select id="claim-policy" data-testid="select-claim-policy" value={policyId} onChange={(event) => setPolicyId(event.target.value)} disabled={policiesQuery.isLoading || policiesQuery.isError} className="min-h-11 w-full rounded-lg border border-input bg-background px-3 text-sm focus:border-primary focus:outline-none"><option value="">No policy selected</option>{(policiesQuery.data ?? []).map((policy) => <option key={policy.id} value={policy.id}>{policy.label}</option>)}</select>{policiesQuery.isError && <p className="mt-2 text-xs text-muted-foreground">Saved policies could not load. You can continue without one.</p>}</div>
            {error && <p role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</p>}
            <button type="submit" data-testid="button-create-claim" disabled={createClaim.isPending} className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50">{createClaim.isPending ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden /> : <FileText className="h-4 w-4" aria-hidden />}Create claim</button>
          </form>
        </section>
        <section aria-labelledby="existing-claims" className="rounded-3xl border border-card-border bg-[hsl(176_30%_94%)] p-5 sm:p-7"><div className="flex items-center justify-between gap-3"><div><p className="text-xs font-bold uppercase tracking-[0.13em] text-primary">Your workspace</p><h2 id="existing-claims" className="mt-1 font-display text-2xl">Saved claims</h2></div>{!isLoading && !isError && <span className="rounded-full bg-card px-2.5 py-1 text-xs font-semibold">{claims?.length ?? 0}</span>}</div>
          {isLoading ? <div className="mt-5 space-y-3" aria-busy="true" aria-label="Loading saved claims">{[1, 2].map((x) => <div key={x} className="h-20 animate-pulse rounded-xl bg-card/70" />)}</div>
            : isError ? <div role="alert" className="mt-5 rounded-xl border border-destructive/25 bg-card p-4"><p className="text-sm font-semibold">Your claims could not load.</p><button type="button" className={`${actionClass()} mt-3`} onClick={() => void refetch()}>Try again</button></div>
            : claims?.length ? <ul className="mt-5 space-y-2">{claims.map((claim) => <li key={claim.id}><Link data-testid={`link-open-claim-${claim.id}`} href={`/workspace/claim/${encodeURIComponent(claim.id)}`} className="flex min-h-[72px] items-center gap-3 rounded-xl border border-card-border bg-card px-4 py-3 transition-colors hover:border-primary/50 focus-visible:outline-2 focus-visible:outline-ring"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-secondary text-primary"><FileText className="h-4 w-4" aria-hidden /></span><span className="min-w-0 flex-1"><span className="block truncate font-semibold">{claim.title}</span><span className="mt-1 block text-xs text-muted-foreground">{claimStatusLabel(claim.status)} · {money(claim.totalExpenses)} recorded</span></span><ChevronRight className="h-4 w-4 text-muted-foreground" aria-hidden /></Link></li>)}</ul>
            : <div className="mt-5 rounded-xl border border-dashed border-primary/30 bg-card/70 p-5"><span className="grid h-10 w-10 place-items-center rounded-xl bg-secondary text-primary"><ShieldCheck className="h-5 w-5" aria-hidden /></span><h3 className="mt-3 font-semibold">No claim records yet</h3><p className="mt-1 text-sm leading-6 text-muted-foreground">Create a record when you’re ready. Your saved claim will remain available here.</p></div>}
        </section>
      </div>
    </main>
  );
}
