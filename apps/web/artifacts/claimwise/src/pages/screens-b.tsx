import { useEffect } from 'react';
import { Link } from 'wouter';
import { ArrowLeft, RefreshCw } from 'lucide-react';
import { ClaimWorkspacePage } from './claim-workspace';
import ClaimChooserPage from './claim-chooser';
import ReviewPackagePage from './review-package';

export function ChatScreen({ claimId }: { claimId: string }) {
  return <ClaimWorkspacePage claimId={claimId} />;
}

export function ClaimChooserScreen() {
  return <ClaimChooserPage />;
}

export function ReviewScreen() {
  return <ReviewPackagePage />;
}

export function StatusScreen() {
  useEffect(() => { document.title = 'Status Update — Claimwise'; }, []);
  return (
    <main className="mx-auto max-w-5xl space-y-7 px-5 py-8 sm:px-8 sm:py-12">
      <header>
        <p className="text-xs font-bold uppercase tracking-[0.14em] text-primary">Claim records</p>
        <h1 className="mt-2 font-display text-4xl">Status Update</h1>
      </header>
      <section className="max-w-3xl rounded-3xl border border-card-border bg-card p-6 sm:p-9">
        <span className="grid h-12 w-12 place-items-center rounded-2xl bg-secondary text-primary"><RefreshCw className="h-5 w-5" aria-hidden /></span>
        <h2 className="mt-5 font-display text-2xl">Record updates in a claim workspace.</h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">Choose a claim to record a status and note. Claimwise records what you enter; only your insurer can decide coverage or payment.</p>
        <Link href="/workspace/claim" className="mt-6 inline-flex min-h-11 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-semibold text-primary-foreground hover:bg-primary/90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
          <ArrowLeft className="h-4 w-4" aria-hidden /> Choose a claim
        </Link>
      </section>
    </main>
  );
}

