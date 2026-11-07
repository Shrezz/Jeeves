import { PolicySearch } from '@/components/policy-search';
import { PolicyDeclarations, policyDetailsPath } from '@/components/policy-declarations';
import { Link } from 'wouter';
import { useEffect, useRef, useState, type ChangeEvent, type DragEvent, type FormEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getListPoliciesQueryKey, useCompletePolicyUpload, useInitiatePolicyUpload, useListPolicies } from '@workspace/api-client-react';
import type { Policy } from '@workspace/api-client-react';
import { ArrowDownToLine, ArrowRight, Check, CheckCircle2, CircleAlert, FileText, FolderOpen, LockKeyhole, UploadCloud } from 'lucide-react';
import { Btn, cx, inputCls } from '@/components/cw';

export type Go = (s: ScreenId) => void;
export type ScreenId = 'upload' | 'dashboard' | 'chat' | 'review' | 'status';

const maxBytes = 20 * 1024 * 1024;
const basePath = import.meta.env.BASE_URL.replace(/\/$/, '');

function documentHref(url: string) {
  if (/^https?:\/\//i.test(url)) return url;
  const path = url.startsWith('/') ? url : `/${url}`;
  return basePath && !path.startsWith(`${basePath}/`) && path !== basePath ? `${basePath}${path}` : path;
}

function formatBytes(bytes: number) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(date: string) {
  const parsed = new Date(date);
  return Number.isNaN(parsed.getTime()) ? 'Date unavailable' : new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(parsed);
}

function PolicyRow({ policy }: { policy: Policy }) {
  return (
    <article data-testid={`card-policy-${policy.id}`} className="min-w-0 rounded-xl border border-card-border bg-background/60 p-4">
      <h3 data-testid={`text-policy-label-${policy.id}`} className="font-semibold leading-snug [overflow-wrap:anywhere]">{policy.label}</h3>
      <p className="mt-1 text-sm text-muted-foreground [overflow-wrap:anywhere]">{policy.fileName}</p>
      <p className="mt-1 text-xs text-muted-foreground">{formatBytes(policy.size)} · Saved {formatDate(policy.createdAt)}</p>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 border-t pt-2 text-sm font-semibold text-primary">
        <Link href={policyDetailsPath(policy.id)} aria-label={`View policy details for ${policy.label}`} className="py-1 hover:underline">View policy details</Link>
        <a data-testid={`link-download-policy-${policy.id}`} href={documentHref(policy.documentUrl)} download={policy.fileName} className="inline-flex items-center gap-1 py-1 hover:underline">
          <ArrowDownToLine className="h-4 w-4" aria-hidden /> Download PDF
        </a>
      </div>
    </article>
  );
}

function PolicyList({ compact = false, onAdd }: { compact?: boolean; onAdd?: () => void }) {
  const { data: policies, isLoading, isError, refetch } = useListPolicies({
    query: { queryKey: getListPoliciesQueryKey(), staleTime: 30_000, refetchOnWindowFocus: true },
  });
  const sorted = [...(policies ?? [])].sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  if (isLoading) {
    return <div aria-busy="true" aria-label="Loading saved policies" className="space-y-3">{[0, 1].map((item) => <div key={item} className="h-24 animate-pulse rounded-2xl bg-muted" />)}</div>;
  }
  if (isError) {
    return <div role="alert" className="rounded-2xl border border-destructive/30 bg-destructive/5 p-5"><p className="font-semibold">Your policies didn’t load.</p><p className="mt-1 text-sm text-muted-foreground">Check your connection and try again.</p><Btn variant="outline" className="mt-4" onClick={() => { void refetch(); }}>Try again</Btn></div>;
  }
  if (!sorted.length) {
    return compact ? <p className="text-sm text-muted-foreground">No saved policies yet. Your first one will appear here.</p> : (
      <div className="rounded-3xl border border-dashed border-[hsl(178_25%_68%)] bg-[hsl(176_30%_94%)] px-6 py-12 text-center sm:px-10">
        <span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-card text-primary"><FolderOpen className="h-6 w-6" aria-hidden /></span>
        <h2 className="mt-5 font-display text-2xl">Your policy folder starts here.</h2>
        <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-muted-foreground">Add a PDF to keep your homeowner policy stored privately and ready when you need it. Nothing is saved until the upload is complete.</p>
        <Btn className="mt-6" onClick={onAdd}>Add your policy <ArrowRight className="h-4 w-4" aria-hidden /></Btn>
      </div>
    );
  }
  return <div className="space-y-3">{sorted.map((policy) => <PolicyRow key={policy.id} policy={policy} />)}</div>;
}

type UploadTicket = { id: string; uploadURL: string; file: File; uploaded: boolean; createdAt: number };

function putPdf(url: string, file: File, onProgress: (value: number) => void) {
  return new Promise<void>((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open('PUT', url);
    request.setRequestHeader('Content-Type', 'application/pdf');
    request.timeout = 120_000;
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)));
    };
    request.onload = () => request.status >= 200 && request.status < 300 ? resolve() : reject(new Error('The secure file transfer did not complete. Please try again.'));
    request.onerror = () => reject(new Error('We couldn’t reach secure document storage. Check your connection and retry.'));
    request.ontimeout = () => reject(new Error('The upload took too long. Your details are still here; try again.'));
    request.onabort = () => reject(new Error('The upload was interrupted. Try again when you’re ready.'));
    request.send(file);
  });
}

type UploadOutcomeKind = 'form' | 'success' | 'failed';

function UploadOutcome({
  kind,
  policy,
  checking,
  lookupError,
  failureReason,
  onRetry,
  onChooseAnother,
  onPolicies,
  onUploadAnother,
}: {
  kind: UploadOutcomeKind;
  policy?: Policy;
  checking: boolean;
  lookupError: boolean;
  failureReason: string;
  onRetry: () => void;
  onChooseAnother: () => void;
  onPolicies: () => void;
  onUploadAnother: () => void;
}) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const verified = kind === 'success' && !!policy;
  const missing = kind === 'success' && !checking && !lookupError && !policy;

  useEffect(() => {
    headingRef.current?.focus();
    if (verified) document.title = 'Saved policy — Claimwise';
    else if (kind === 'failed') document.title = 'Upload Failed — Claimwise';
    else if (checking) document.title = 'Checking saved policy — Claimwise';
    else if (lookupError) document.title = 'Couldn’t verify save — Claimwise';
    else if (missing) document.title = 'Policy not found — Claimwise';
  }, [verified, kind, checking, lookupError, missing]);

  if (kind === 'success' && checking && !policy) {
    return (
      <section className="mx-auto max-w-3xl rounded-3xl border border-card-border bg-card p-6 sm:p-10" aria-busy="true" aria-live="polite">
        <div className="h-12 w-12 animate-pulse rounded-2xl bg-secondary" />
        <h1 ref={headingRef} tabIndex={-1} className="mt-6 font-display text-3xl sm:text-4xl">Checking your saved policy</h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">We’re checking your private policy list before confirming this document was saved.</p>
        <div className="mt-7 h-20 animate-pulse rounded-2xl bg-muted" />
      </section>
    );
  }

  if (kind === 'success' && policy) {
    return (
      <section data-testid="panel-upload-success" className="mx-auto max-w-3xl overflow-hidden rounded-3xl border border-[hsl(155_24%_75%)] bg-[hsl(150_28%_95%)]">
        <div className="h-2 bg-primary" />
        <div className="p-6 sm:p-10">
          <div className="flex items-start gap-4">
            <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-card text-primary"><CheckCircle2 className="h-6 w-6" aria-hidden /></span>
            <div className="min-w-0">
              <p className="text-xs font-bold uppercase tracking-[0.14em] text-primary">Saved to your private folder</p>
              <h1 ref={headingRef} tabIndex={-1} data-testid="text-upload-outcome-title" className="mt-2 font-display text-3xl leading-tight sm:text-4xl">Policy saved</h1>
            </div>
          </div>
          <article data-testid={`card-uploaded-policy-${policy.id}`} className="mt-7 flex flex-col gap-4 rounded-2xl border border-[hsl(155_24%_82%)] bg-card p-4 sm:flex-row sm:items-center">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-secondary text-primary"><FileText className="h-5 w-5" aria-hidden /></span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="font-semibold [overflow-wrap:anywhere]">{policy.label}</h2>
                <span className="inline-flex items-center gap-1 rounded-full bg-secondary px-2.5 py-1 text-xs font-semibold text-secondary-foreground"><Check className="h-3 w-3" aria-hidden /> Saved</span>
              </div>
              <p className="mt-1 text-sm text-muted-foreground [overflow-wrap:anywhere]">{policy.fileName}</p>
              <p className="mt-1 text-xs text-muted-foreground">{formatBytes(policy.size)} <span aria-hidden>·</span> Added {formatDate(policy.createdAt)}</p>
            </div>
            <a data-testid="link-outcome-download" href={documentHref(policy.documentUrl)} download={policy.fileName} className="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-lg border px-4 text-sm font-semibold text-foreground transition-colors hover:border-primary hover:text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
              <ArrowDownToLine className="h-4 w-4" aria-hidden /> Download PDF
            </a>
          </article>
          <PolicyDeclarations policy={policy} />
          <PolicySearch key={policy.id} policy={policy} />
          <div className="mt-7 flex flex-col gap-3 sm:flex-row">
            <Btn data-testid="button-outcome-my-policies" onClick={onPolicies}>Dashboard <ArrowRight className="h-4 w-4" aria-hidden /></Btn>
            <Btn data-testid="button-outcome-upload-another" variant="outline" onClick={onUploadAnother}>Upload another</Btn>
          </div>
        </div>
      </section>
    );
  }

  if (kind === 'success') {
    return (
      <section data-testid="panel-upload-unverified" role="alert" aria-live="polite" className="mx-auto max-w-3xl rounded-3xl border border-[hsl(38_70%_70%)] bg-[hsl(38_80%_95%)] p-6 sm:p-10">
        <span className="grid h-12 w-12 place-items-center rounded-2xl bg-card text-[hsl(30_80%_32%)]"><CircleAlert className="h-6 w-6" aria-hidden /></span>
        <h1 ref={headingRef} tabIndex={-1} data-testid="text-upload-outcome-title" className="mt-6 font-display text-3xl sm:text-4xl">{lookupError ? 'We couldn’t verify the save' : 'Policy not found'}</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
          {lookupError
            ? 'Your policy list is unavailable right now, so we can’t confirm this document from this link. Check your Dashboard when your connection is available.'
            : missing
              ? 'This policy isn’t in the saved list for your account. No upload is being presented as complete.'
              : 'We’re checking your private policy list before confirming this document was saved.'}
        </p>
        <div className="mt-7 flex flex-col gap-3 sm:flex-row">
          <Btn data-testid="button-outcome-my-policies" onClick={onPolicies}>Dashboard <ArrowRight className="h-4 w-4" aria-hidden /></Btn>
          <Btn data-testid="button-outcome-choose-another" variant="outline" onClick={onChooseAnother}>Choose another PDF</Btn>
        </div>
      </section>
    );
  }

  return (
    <section data-testid="panel-upload-failed" role="alert" aria-live="polite" className="mx-auto max-w-3xl overflow-hidden rounded-3xl border border-[hsl(4_50%_82%)] bg-[hsl(4_65%_97%)]">
      <div className="h-2 bg-destructive" />
      <div className="p-6 sm:p-10">
        <div className="flex items-start gap-4">
          <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-card text-destructive"><CircleAlert className="h-6 w-6" aria-hidden /></span>
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-destructive">Save not confirmed</p>
            <h1 ref={headingRef} tabIndex={-1} data-testid="text-upload-outcome-title" className="mt-2 font-display text-3xl sm:text-4xl">Upload Failed</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              {failureReason
                ? 'The upload could not be confirmed. The reason we received is below. A completion response can be interrupted, so check your Dashboard before trying again.'
                : 'There’s no confirmed upload attempt on this page. If you expected a document here, check your Dashboard before retrying.'}
            </p>
          </div>
        </div>
        <div className="mt-6 rounded-xl border border-[hsl(4_40%_86%)] bg-card px-4 py-3 text-sm">
          <p className="font-semibold text-foreground">{failureReason ? 'What happened' : 'No attempt details available'}</p>
          <p data-testid="text-upload-failure-reason" className="mt-1 leading-6 text-muted-foreground">{failureReason || 'This result was opened directly. Return to Add policy to choose a PDF.'}</p>
        </div>
        <div className="mt-7 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
          <Btn data-testid="button-outcome-retry" onClick={onRetry}><ArrowRight className="h-4 w-4" aria-hidden /> Retry upload</Btn>
          <Btn data-testid="button-outcome-choose-another" variant="outline" onClick={onChooseAnother}>Choose another PDF</Btn>
          <Btn data-testid="button-outcome-my-policies" variant="ghost" onClick={onPolicies}>Dashboard</Btn>
        </div>
      </div>
    </section>
  );
}

export function UploadScreen({
  go,
  outcome = 'form',
  policyId,
  onRoute,
}: {
  go: Go;
  outcome?: UploadOutcomeKind;
  policyId?: string;
  onRoute: (path: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [label, setLabel] = useState('');
  const [deductible, setDeductible] = useState('');
  const [fileError, setFileError] = useState('');
  const [formError, setFormError] = useState('');
  const [transferError, setTransferError] = useState('');
  const [stage, setStage] = useState<'idle' | 'requesting' | 'uploading' | 'saving' | 'error' | 'saved'>('idle');
  const [progress, setProgress] = useState(0);
  const [ticket, setTicket] = useState<UploadTicket | null>(null);
  const [saved, setSaved] = useState<Policy | null>(null);
  const [dragging, setDragging] = useState(false);
  const initiate = useInitiatePolicyUpload();
  const complete = useCompletePolicyUpload();
  const queryClient = useQueryClient();
  const active = useRef(true);
  useEffect(() => {
    active.current = true;
    return () => { active.current = false; };
  }, []);
  const { data: policies, isLoading: policiesLoading, isError: policiesError } = useListPolicies({
    query: { queryKey: getListPoliciesQueryKey(), staleTime: 30_000 },
  });
  const busy = stage === 'requesting' || stage === 'uploading' || stage === 'saving';
  const listedPolicy = policyId ? policies?.find((item) => item.id === policyId) : undefined;
  const confirmedPolicy = listedPolicy ?? (saved?.id === policyId ? saved : undefined) ?? undefined;

  const acceptFile = (next: File | undefined) => {
    if (busy || !next) return;
    setFileError('');
    setTransferError('');
    if (!/\.pdf$/i.test(next.name) || (next.type && next.type !== 'application/pdf')) {
      setFileError('Choose a PDF file. Other file types aren’t accepted.');
      return;
    }
    if (next.size < 1 || next.size > maxBytes) {
      setFileError('The PDF must be smaller than 20 MB.');
      return;
    }
    setFile(next);
    setTicket(null);
    setSaved(null);
    setStage('idle');
    setProgress(0);
    if (!label.trim()) setLabel(next.name.replace(/\.pdf$/i, '').slice(0, 120));
  };

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => acceptFile(event.target.files?.[0]);
  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    acceptFile(event.dataTransfer.files?.[0]);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) return;
    setFormError('');
    setTransferError('');
    if (!file) { setFileError('Choose your policy PDF before continuing.'); return; }
    if (!label.trim() || label.trim().length > 120) { setFormError('Enter a policy label between 1 and 120 characters.'); return; }
    const numericDeductible = deductible.trim() === '' ? null : Number(deductible);
    if (numericDeductible !== null && (!Number.isFinite(numericDeductible) || numericDeductible < 0 || numericDeductible > 100_000_000)) {
      setFormError('Enter a deductible from 0 to 100,000,000, or leave it blank.');
      return;
    }

    let currentTicket: UploadTicket | null = ticket;
    setStage('requesting');
    try {
      if (!currentTicket || currentTicket.file !== file || currentTicket.createdAt < Date.now() - 14 * 60 * 1000) {
        const response = await initiate.mutateAsync({ data: { fileName: file.name, size: file.size } });
        if (!active.current) return;
        currentTicket = { ...response, file, uploaded: false, createdAt: Date.now() };
        setTicket(currentTicket);
      }
      if (!currentTicket) return;
      if (!currentTicket.uploaded) {
        setStage('uploading');
        setProgress(0);
        await putPdf(currentTicket.uploadURL, file, setProgress);
        if (!active.current) return;
        currentTicket = { ...currentTicket, file, uploaded: true };
        setTicket(currentTicket);
      }
      setStage('saving');
      const policy = await complete.mutateAsync({
        id: currentTicket.id,
        data: { label: label.trim(), deductible: numericDeductible },
      });
      if (!active.current) return;
      queryClient.setQueryData(getListPoliciesQueryKey(), (previous: Policy[] | undefined) => {
        const existing = previous ?? [];
        return [policy, ...existing.filter((item) => item.id !== policy.id)];
      });
      setSaved(policy);
      setStage('saved');
      onRoute(`/workspace/upload/success/${encodeURIComponent(policy.id)}`);
      void queryClient.invalidateQueries({ queryKey: getListPoliciesQueryKey() }).catch(() => undefined);
    } catch (error) {
      if (!active.current) return;
      setStage('error');
      const reason = error instanceof Error ? error.message : 'We couldn’t confirm the upload. Your details are still here; check your Dashboard before retrying.';
      setTransferError(reason);
      onRoute('/workspace/upload/failed');
    }
  };

  const retryUpload = () => onRoute('/workspace/upload');
  const chooseAnother = () => {
    onRoute('/workspace/upload');
    window.requestAnimationFrame(() => inputRef.current?.click());
  };
  const uploadAnother = () => {
    setFile(null);
    setLabel('');
    setDeductible('');
    setFileError('');
    setFormError('');
    setTransferError('');
    setTicket(null);
    setSaved(null);
    setStage('idle');
    setProgress(0);
    if (inputRef.current) inputRef.current.value = '';
    onRoute('/workspace/upload');
  };

  return (
    <div className="mx-auto max-w-6xl space-y-10 px-5 py-8 sm:px-8 sm:py-12">
      {outcome !== 'form' ? (
        <UploadOutcome
          kind={outcome}
          policy={confirmedPolicy}
          checking={outcome === 'success' && policiesLoading}
          lookupError={outcome === 'success' && policiesError && !confirmedPolicy}
          failureReason={outcome === 'failed' ? transferError : ''}
          onRetry={retryUpload}
          onChooseAnother={chooseAnother}
          onPolicies={() => go('dashboard')}
          onUploadAnother={uploadAnother}
        />
      ) : (
        <>
      <header className="grid gap-7 lg:grid-cols-[1fr_auto] lg:items-end">
        <div className="max-w-2xl">
          <p className="text-sm font-semibold uppercase tracking-[0.14em] text-primary">Your private policy folder</p>
          <h1 className="mt-3 font-display text-4xl leading-tight sm:text-5xl">Add your policy</h1>
          <p className="mt-3 max-w-xl text-base leading-7 text-muted-foreground">{import.meta.env.VITE_LOCAL_POLICY_SEARCH ? 'Save your policy PDF and search its text for the clauses you need after a loss.' : 'Store the original policy PDF in your private folder.'}</p>
        </div>
        <div className="rounded-2xl border bg-card px-4 py-3 text-sm text-muted-foreground">
          <span className="flex items-center gap-2 font-semibold text-foreground"><LockKeyhole className="h-4 w-4 text-primary" aria-hidden /> Private document storage</span>
          <span className="mt-1 block pl-6">Upload transfers securely to your account.</span>
        </div>
      </header>

        <div className="grid gap-8 lg:grid-cols-[minmax(0,1.35fr)_minmax(17rem,.65fr)]">
          <form onSubmit={submit} noValidate aria-busy={busy} className="rounded-3xl border bg-card p-5 shadow-[0_16px_50px_-38px_hsl(192_30%_12%/.28)] sm:p-8">
            <h2 className="font-display text-2xl">Policy document</h2>
            <p className="mt-1 text-sm text-muted-foreground">Choose the PDF file you want to keep on hand.</p>
            <div
              onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
              onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false); }}
              onDrop={onDrop}
              className={cx('mt-6 rounded-2xl border-2 border-dashed p-6 text-center transition-colors focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ring sm:p-9', dragging ? 'border-primary bg-secondary/70' : 'border-input bg-background/50', fileError && 'border-destructive')}
            >
              <input ref={inputRef} id="policy-pdf" data-testid="input-policy-pdf" type="file" accept=".pdf,application/pdf" className="sr-only" onChange={onFileChange} aria-describedby="pdf-help pdf-error" disabled={busy} />
              <label htmlFor="policy-pdf" className="mx-auto flex max-w-lg cursor-pointer flex-col items-center">
                <span className="grid h-12 w-12 place-items-center rounded-2xl bg-secondary text-primary"><UploadCloud className="h-6 w-6" aria-hidden /></span>
                <span className="mt-4 font-semibold">{file ? 'Choose a different PDF' : 'Choose a PDF or drop it here'}</span>
                <span id="pdf-help" className="mt-1 text-sm text-muted-foreground">PDF only · maximum 20 MB</span>
              </label>
              {file && <div className="mx-auto mt-5 flex max-w-lg items-center gap-3 rounded-xl border bg-card p-3 text-left">
                <FileText className="h-5 w-5 shrink-0 text-primary" aria-hidden />
                <div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold">{file.name}</p><p className="text-xs text-muted-foreground">{formatBytes(file.size)}</p></div>
                {stage === 'requesting' && <span className="text-sm font-semibold text-primary">Preparing…</span>}
                {stage === 'uploading' && <span className="text-sm font-semibold tabular-nums text-primary">Uploading {progress}%</span>}
                {stage === 'saving' && <span className="text-sm font-semibold text-primary">Saving…</span>}
              </div>}
              {stage === 'uploading' && <div className="mx-auto mt-3 max-w-lg" aria-label={`Upload progress ${progress}%`} role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}><div className="h-2 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary transition-[width] duration-200" style={{ width: `${progress}%` }} /></div></div>}
            </div>
            <p id="pdf-error" data-testid="text-file-error" className="mt-2 min-h-5 text-sm text-destructive" role={fileError ? 'alert' : undefined}>{fileError}</p>
            <div className="mt-5 grid gap-5 sm:grid-cols-2">
              <div>
                <label htmlFor="policy-label" className="text-sm font-semibold">Policy label <span className="text-destructive" aria-hidden>*</span></label>
                <input id="policy-label" data-testid="input-policy-label" className={cx(inputCls, 'mt-2')} value={label} onChange={(event) => setLabel(event.target.value)} maxLength={120} required aria-describedby="label-help" disabled={busy} />
                <p id="label-help" className="mt-1 text-xs text-muted-foreground">A name you’ll recognize · up to 120 characters</p>
              </div>
              <div>
                <label htmlFor="policy-deductible" className="text-sm font-semibold">Deductible <span className="font-normal text-muted-foreground">(optional)</span></label>
                <div className="relative mt-2"><span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">$</span><input id="policy-deductible" data-testid="input-policy-deductible" className={cx(inputCls, 'pl-7')} type="number" min="0" max="100000000" step="0.01" inputMode="decimal" value={deductible} onChange={(event) => setDeductible(event.target.value)} disabled={busy} /></div>
                <p className="mt-1 text-xs text-muted-foreground">Enter the amount from your declarations page.</p>
              </div>
            </div>
            {formError && <p role="alert" className="mt-4 rounded-lg bg-destructive/5 px-3 py-2 text-sm text-destructive">{formError}</p>}
            {transferError && <p role="alert" data-testid="text-upload-error" className="mt-4 rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">{transferError}</p>}
            <div className="mt-6 flex flex-col gap-3 border-t pt-5 sm:flex-row sm:items-center sm:justify-between">
              <p className="max-w-sm text-xs leading-5 text-muted-foreground">{import.meta.env.VITE_LOCAL_POLICY_SEARCH ? 'Text-based PDFs can be searched after indexing. Scanned images are not supported.' : 'Your original PDF is saved in private document storage.'}</p>
              <Btn type="submit" data-testid="button-save-policy" disabled={busy || !file} className="min-w-44 justify-center">
                {stage === 'requesting' ? 'Preparing upload…' : stage === 'uploading' ? `Uploading ${progress}%` : stage === 'saving' ? (import.meta.env.VITE_LOCAL_POLICY_SEARCH ? 'Saving and indexing…' : 'Saving policy…') : stage === 'error' ? 'Retry save' : 'Save policy'}
                {stage !== 'requesting' && stage !== 'uploading' && stage !== 'saving' && <ArrowRight className="h-4 w-4" aria-hidden />}
              </Btn>
            </div>
          </form>
          <aside className="space-y-5">
            <div className="rounded-3xl bg-[hsl(178_28%_22%)] p-6 text-[hsl(40_33%_97%)] sm:p-7">
              <p className="text-xs font-bold uppercase tracking-[0.14em] text-[hsl(166_42%_78%)]">A clear first step</p>
              <h2 className="mt-3 font-display text-2xl">Keep the original close.</h2>
              <p className="mt-2 text-sm leading-6 text-[hsl(40_20%_85%)]">The upload stores your PDF and the label you choose. It doesn’t open a claim, contact your insurer, or determine what’s covered.</p>
            </div>
            <div className="rounded-2xl border bg-card p-5">
              <div className="flex items-center justify-between gap-3">
                <h2 className="font-semibold">Recently saved</h2>
                <button type="button" data-testid="button-my-policies" className="text-sm font-semibold text-primary hover:underline" onClick={() => go('dashboard')}>Dashboard</button>
              </div>
              <div className="mt-4"><PolicyList compact onAdd={() => go('upload')} /></div>
            </div>
          </aside>
        </div>
        </>
      )}
    </div>
  );
}

