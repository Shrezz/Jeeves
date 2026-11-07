import { useEffect } from 'react';
import { Link } from 'wouter';
import { ArrowRight, ClipboardList, MessageSquareText } from 'lucide-react';

type EmptyKind = 'review' | 'status';

const content = {
  review: {
    title: 'Review Claim',
    eyebrow: 'Policy review',
    description: 'There is no review package in your account. Jeeves does not currently create or store claim review packages.',
    detail: 'When this workflow is available, this page will show real information saved to your account. Nothing has been reviewed or prepared.',
    Icon: ClipboardList,
  },
  status: {
    title: 'Status Update',
    eyebrow: 'Claim status',
    description: 'There is no status history in your account. Jeeves does not currently track claim status updates.',
    detail: 'No claim activity is being tracked here. This space will only show status history if that feature becomes available and real records exist.',
    Icon: MessageSquareText,
  },
} satisfies Record<EmptyKind, { title: string; eyebrow: string; description: string; detail: string; Icon: typeof ClipboardList }>;

export default function WorkspaceEmptyPage({ kind }: { kind: EmptyKind }) {
  const page = content[kind];
  const Icon = page.Icon;

  useEffect(() => {
    document.title = `${page.title} — Jeeves`;
  }, [page.title]);

  return (
    <div className="mx-auto max-w-6xl space-y-8 px-5 py-8 sm:px-8 sm:py-12">
      <header>
        <p className="text-sm font-semibold uppercase tracking-[0.14em] text-primary">{page.eyebrow}</p>
        <h1 className="mt-3 font-display text-4xl sm:text-5xl">{page.title}</h1>
      </header>
      <section aria-labelledby="workspace-empty-heading" className="relative max-w-3xl overflow-hidden rounded-3xl border border-[hsl(178_25%_68%)] bg-[hsl(176_30%_94%)] p-6 sm:p-10">
        <div className="absolute right-5 top-5 h-24 w-24 rounded-full border border-[hsl(178_30%_80%)] opacity-60 sm:right-10 sm:top-8 sm:h-36 sm:w-36" aria-hidden />
        <span className="relative grid h-14 w-14 place-items-center rounded-2xl border border-card-border bg-card text-primary"><Icon className="h-6 w-6" aria-hidden /></span>
        <p className="relative mt-6 text-xs font-bold uppercase tracking-[0.14em] text-primary">No records available</p>
        <h2 id="workspace-empty-heading" className="relative mt-2 max-w-xl font-display text-3xl leading-tight sm:text-4xl">Nothing here yet.</h2>
        <p className="relative mt-3 max-w-xl text-sm leading-6 text-muted-foreground">{page.description}</p>
        <p className="relative mt-4 max-w-xl border-l-2 border-primary/40 pl-4 text-sm leading-6 text-muted-foreground">{page.detail}</p>
        <div className="relative mt-7 flex flex-col gap-3 sm:flex-row">
          <Link href="/workspace/dashboard" className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground shadow-[0_1px_0_hsl(178_64%_18%)] transition-colors hover:bg-[hsl(178_64%_22%)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
            Dashboard <ArrowRight className="h-4 w-4" aria-hidden />
          </Link>
          <Link href="/workspace/upload" className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-input bg-card px-4 py-2 text-sm font-semibold text-foreground transition-colors hover:border-primary hover:text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
            Upload Policy
          </Link>
        </div>
      </section>
    </div>
  );
}
