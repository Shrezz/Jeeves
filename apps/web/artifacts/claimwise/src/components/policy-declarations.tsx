import { Link } from 'wouter';
import { getGetPolicyDeclarationsQueryKey, useGetPolicyDeclarations, type Policy, type PolicyDeclaration } from '@workspace/api-client-react';

export function policyDetailsPath(id: string) {
  return '/workspace/upload/success/' + encodeURIComponent(id);
}

function DeclarationRows({ fields }: { fields: PolicyDeclaration[] }) {
  return <dl className="mt-2 divide-y divide-border">
    {fields.map((field, i) => <div key={i} className="py-2.5">
      <dt className="flex flex-wrap items-baseline justify-between gap-x-3 text-xs font-semibold text-muted-foreground">
        <span>{field.label}</span><span className="font-normal">PDF p. {field.page}</span>
      </dt>
      <dd className="mt-1 text-sm font-medium leading-5 [overflow-wrap:anywhere]">{field.value}</dd>
    </div>)}
  </dl>;
}

export function PolicyDeclarations({ policy, compact = false }: { policy: Policy; compact?: boolean }) {
  const local = Boolean(policy.ingestionStatus);
  const query = useGetPolicyDeclarations(policy.id, { query: {
    queryKey: getGetPolicyDeclarationsQueryKey(policy.id), enabled: local, staleTime: Infinity, retry: false,
  } });
  const fields = query.data?.fields ?? [];
  const primary = fields.filter(f => compact ? f.kind === 'deductible' : ['number', 'deductible', 'term', 'limit'].includes(f.kind));
  const other = compact ? [] : fields.filter(f => !primary.includes(f));
  const manual = policy.deductible !== null && <p className="mt-2 text-xs text-muted-foreground">
    Deductible entered at upload: <strong>{policy.deductible.toLocaleString('en-US', { style: 'currency', currency: 'USD' })}</strong>
  </p>;
  if (!local) return <>{manual}</>;
  return <section aria-label="Policy declarations" className={compact ? 'mt-3' : 'mt-5 rounded-2xl border border-card-border bg-card p-5'}>
    {!compact && <><h2 className="font-display text-xl">Policy declarations</h2>
      <p className="mt-1 text-sm text-muted-foreground">As written in your uploaded PDF.</p></>}
    {query.isPending ? <p role="status" className="mt-2 text-sm">Reading your PDF…</p>
      : query.isError ? <p className="mt-2 text-sm">Couldn’t load the policy details. <button className="font-semibold text-primary underline" onClick={() => void query.refetch()}>Try again</button></p>
      : <>
        {primary.length > 0 && <DeclarationRows fields={primary} />}
        {!fields.length && <p className="mt-2 text-sm text-muted-foreground">No labeled declarations could be read. Check the original PDF for policy terms.</p>}
        {compact && fields.length > 0 && !primary.length && <p className="text-sm text-muted-foreground">No deductible was identified in the declarations.</p>}
        {other.length > 0 && <details className="mt-2 rounded-xl bg-secondary/45 px-3 py-2">
          <summary className="cursor-pointer text-sm font-semibold text-primary">More policy details ({other.length})</summary>
          <DeclarationRows fields={other} />
        </details>}
      </>}
    {manual}
    {compact && <Link href={policyDetailsPath(policy.id)} className="mt-2 inline-flex text-sm font-semibold text-primary hover:underline">View policy details</Link>}
  </section>;
}
