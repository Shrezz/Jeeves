import { useEffect } from 'react';
import { useClerk, useUser } from '@clerk/react';
import { CalendarDays, Mail, UserRound } from 'lucide-react';

function accountDate(createdAt: Date | null | undefined) {
  if (!createdAt) return 'Not provided by your account';
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'long' }).format(createdAt);
}

export default function AccountPage() {
  const { user } = useUser();
  const { openUserProfile } = useClerk();

  useEffect(() => {
    document.title = 'Your Account — Jeeves';
  }, []);

  const name = user?.fullName || [user?.firstName, user?.lastName].filter(Boolean).join(' ') || '';
  const email = user?.primaryEmailAddress?.emailAddress || '';

  return (
    <div className="mx-auto max-w-6xl space-y-8 px-5 py-8 sm:px-8 sm:py-12">
      <header className="max-w-2xl">
        <p className="text-sm font-semibold uppercase tracking-[0.14em] text-primary">Your private workspace</p>
        <h1 className="mt-3 font-display text-4xl sm:text-5xl">Your Account</h1>
        <p className="mt-3 leading-7 text-muted-foreground">A read-only summary of the account currently signed in to Jeeves.</p>
      </header>
      <section aria-labelledby="account-summary-heading" className="max-w-3xl overflow-hidden rounded-3xl border border-card-border bg-card shadow-[0_16px_50px_-38px_hsl(192_30%_12%/.28)]">
        <div className="flex items-center gap-4 border-b border-border bg-[hsl(176_30%_94%)] p-5 sm:p-7">
          <span className="grid h-12 w-12 place-items-center rounded-2xl bg-card text-primary"><UserRound className="h-5 w-5" aria-hidden /></span>
          <div>
            <h2 id="account-summary-heading" className="font-display text-2xl">Account summary</h2>
            <p className="mt-1 text-sm text-muted-foreground">Details supplied by your sign-in account.</p>
          </div>
        </div>
        <dl className="divide-y divide-border px-5 sm:px-7">
          <div className="grid gap-2 py-5 sm:grid-cols-[12rem_1fr] sm:items-center">
            <dt className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground"><UserRound className="h-4 w-4" aria-hidden /> Name</dt>
            <dd data-testid="text-account-name" className="break-words text-sm font-medium">{name || 'Not provided by your account'}</dd>
          </div>
          <div className="grid gap-2 py-5 sm:grid-cols-[12rem_1fr] sm:items-center">
            <dt className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground"><Mail className="h-4 w-4" aria-hidden /> Email</dt>
            <dd data-testid="text-account-email" className="break-all text-sm font-medium">{email || 'Not provided by your account'}</dd>
          </div>
          <div className="grid gap-2 py-5 sm:grid-cols-[12rem_1fr] sm:items-center">
            <dt className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground"><CalendarDays className="h-4 w-4" aria-hidden /> Account created</dt>
            <dd data-testid="text-account-created" className="text-sm font-medium">{accountDate(user?.createdAt)}</dd>
          </div>
        </dl>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-5 py-4 sm:px-7">
          <p className="text-xs leading-5 text-muted-foreground">Manage your name and account details with your sign-in provider.</p>
          <button type="button" data-testid="button-edit-account" onClick={() => openUserProfile()} className="rounded-lg border border-border px-4 py-2 text-sm font-semibold text-primary transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">Edit profile</button>
        </div>
      </section>
    </div>
  );
}
