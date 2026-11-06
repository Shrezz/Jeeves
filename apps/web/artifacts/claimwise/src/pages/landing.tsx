import { useEffect } from 'react';
import { Link } from 'wouter';
import { ArrowRight, FileText, LockKeyhole, ShieldCheck } from 'lucide-react';
import { Mark } from '@/components/cw';

export default function Landing() {
  useEffect(() => { document.title = 'Add your policy — Claimwise'; }, []);
  return (
    <div className="min-h-[100dvh]">
      <header className="flex items-center gap-3 px-5 py-4 sm:px-10">
        <Mark className="h-8 w-8" /><span className="text-lg font-bold tracking-tight">Claimwise</span>
        <nav aria-label="Account" className="ml-auto flex items-center gap-2">
          <Link href="/sign-in" data-testid="link-sign-in" className="rounded-lg px-3 py-2 text-sm font-semibold text-muted-foreground transition-colors hover:text-foreground">Sign in</Link>
          <Link href="/sign-up" data-testid="link-sign-up-header" className="rounded-lg bg-primary px-3.5 py-2 text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90">Create account</Link>
        </nav>
      </header>
      <main>
        <section className="cw-enter relative isolate overflow-hidden px-5 pb-16 pt-12 sm:px-10 sm:pb-24 sm:pt-20">
          <div className="pointer-events-none absolute -right-36 -top-28 -z-10 h-[32rem] w-[32rem] rounded-full border border-primary/10 sm:right-[-8rem]">
            <div className="absolute inset-8 rounded-full border border-primary/10" />
            <div className="absolute inset-16 rounded-full border border-primary/10" />
            <div className="absolute inset-24 rounded-full border border-primary/10" />
            <div className="absolute right-1/4 top-1/4 h-44 w-44 rounded-full bg-[hsl(178_38%_82%/.24)] blur-3xl" />
          </div>
          <div className="relative mx-auto grid max-w-6xl gap-12 lg:grid-cols-[1.15fr_.85fr] lg:items-center">
            <div className="max-w-2xl">
              <p className="text-sm font-semibold uppercase tracking-[0.14em] text-primary">A steady place after a loss</p>
              <h1 className="mt-4 font-display text-5xl leading-[1.02] sm:text-7xl">Add your policy</h1>
              <p className="mt-6 max-w-xl text-lg leading-8 text-muted-foreground">When home paperwork gets hard to navigate, start with one clear step: keep your homeowner policy PDF somewhere you can find it.</p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link href="/sign-up" data-testid="link-sign-up" className="inline-flex min-h-12 items-center gap-2 rounded-xl bg-primary px-5 font-semibold text-primary-foreground transition-transform hover:-translate-y-0.5">Create your private folder <ArrowRight className="h-4 w-4" aria-hidden /></Link>
                <Link href="/sign-in" data-testid="link-sign-in-hero" className="inline-flex min-h-12 items-center rounded-xl border bg-card px-5 font-semibold transition-colors hover:border-primary/50">Sign in</Link>
              </div>
              <p className="mt-4 text-xs text-muted-foreground">No insurer connection. No claim filed. Just your document, stored for you.</p>
            </div>
            <aside className="relative mx-auto w-full max-w-md rounded-[1.75rem] border bg-card p-5 shadow-[0_28px_70px_-50px_hsl(192_30%_12%/.4)] sm:p-7" aria-label="Policy storage preview">
              <div className="flex items-center justify-between border-b pb-4">
                <span className="flex items-center gap-2 text-sm font-semibold"><Mark className="h-6 w-6" /> Claimwise</span>
                <span className="rounded-full bg-secondary px-3 py-1 text-xs font-semibold text-secondary-foreground">Your workspace</span>
              </div>
              <div className="py-7">
                <p className="text-xs font-bold uppercase tracking-[0.13em] text-primary">First step</p>
                <h2 className="mt-2 font-display text-3xl">Add your policy</h2>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">Store your PDF and the details you choose to enter.</p>
                <div className="mt-6 flex items-center gap-3 rounded-xl border border-dashed border-primary/35 bg-secondary/40 p-4">
                  <span className="grid h-10 w-10 place-items-center rounded-lg bg-card text-primary"><FileText className="h-5 w-5" aria-hidden /></span>
                  <div><p className="text-sm font-semibold">Home policy PDF</p><p className="mt-0.5 text-xs text-muted-foreground">Private document storage</p></div>
                </div>
              </div>
              <div className="flex items-start gap-3 border-t pt-4 text-xs leading-5 text-muted-foreground">
                <LockKeyhole className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
                <p>Uploads go directly to private document storage. Claimwise does not read or extract policy details yet.</p>
              </div>
            </aside>
          </div>
        </section>

        <section className="border-y bg-card px-5 py-14 sm:px-10 sm:py-16">
          <div className="mx-auto grid max-w-6xl gap-10 md:grid-cols-[.8fr_1.2fr]">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.14em] text-primary">Small steps, clear boundaries</p>
              <h2 className="mt-3 max-w-sm font-display text-3xl leading-tight sm:text-4xl">Paperwork belongs somewhere you trust.</h2>
            </div>
            <div className="grid gap-7 sm:grid-cols-2">
              <article className="flex gap-4">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-secondary text-primary"><ShieldCheck className="h-5 w-5" aria-hidden /></span>
                <div><h3 className="font-semibold">Private by account</h3><p className="mt-2 text-sm leading-6 text-muted-foreground">Your saved policies are tied to your signed-in account and stay available in My policies.</p></div>
              </article>
              <article className="flex gap-4">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-secondary text-primary"><FileText className="h-5 w-5" aria-hidden /></span>
                <div><h3 className="font-semibold">The original stays yours</h3><p className="mt-2 text-sm leading-6 text-muted-foreground">Download the document you uploaded whenever you need to refer back to it.</p></div>
              </article>
              <p className="text-sm leading-6 text-muted-foreground sm:col-span-2">Today Claimwise is for secure document storage and details you enter yourself. Automatic extraction, claim advice, and insurer decisions are not part of this workspace.</p>
            </div>
          </div>
        </section>

        <section className="px-5 py-16 sm:px-10 sm:py-20">
          <div className="mx-auto flex max-w-6xl flex-col gap-6 rounded-3xl bg-[hsl(178_28%_22%)] p-7 text-[hsl(40_33%_97%)] sm:flex-row sm:items-center sm:justify-between sm:p-10">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.14em] text-[hsl(166_42%_78%)]">Ready when you are</p>
              <h2 className="mt-3 font-display text-3xl sm:text-4xl">Start with the policy you already have.</h2>
              <p className="mt-2 max-w-xl text-sm leading-6 text-[hsl(40_20%_85%)]">Create an account, upload a PDF, and keep it within reach. You can add or review documents at your own pace.</p>
            </div>
            <Link href="/sign-up" className="inline-flex min-h-12 shrink-0 items-center justify-center gap-2 rounded-xl bg-[hsl(40_33%_97%)] px-5 font-semibold text-[hsl(178_28%_22%)] transition-transform hover:-translate-y-0.5">Create account <ArrowRight className="h-4 w-4" aria-hidden /></Link>
          </div>
        </section>
      </main>
      <footer className="border-t px-5 py-6 text-xs text-muted-foreground sm:px-10">Claimwise is a document-organizing tool, not an insurer, adjuster, or legal advisor.</footer>
    </div>
  );
}
