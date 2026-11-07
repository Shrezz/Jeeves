import { Link } from 'wouter';
import { ClipboardList, LayoutDashboard, UserRound, ClipboardPlus } from 'lucide-react';
import { Mark } from '@/components/cw';

const destinations = [
  { href: '/workspace/account', label: 'Your Account', Icon: UserRound },
  { href: '/workspace/dashboard', label: 'Dashboard', Icon: LayoutDashboard },
  { href: '/workspace/claim', label: 'Prepare Your Claim', Icon: ClipboardPlus },
  { href: '/workspace/review', label: 'Review Claim', Icon: ClipboardList },
] as const;

export function WorkspaceNav({ path }: { path: string }) {
  const activePath = path.startsWith('/workspace/upload/') ? '/workspace/upload' : path.startsWith('/workspace/claim/') ? '/workspace/claim' : path;

  return (
    <nav aria-label="Workspace" className="border-t border-[hsl(180_14%_84%)] bg-[hsl(176_30%_94%)]">
      <ul className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-4 py-2.5 sm:px-6" data-testid="workspace-navigation">
        {destinations.map(({ href, label, Icon }) => {
          const active = activePath === href;
          return (
            <li key={href} className="shrink-0">
              <Link
                href={href}
                data-testid={`nav-${href.split('/').at(-1)}`}
                aria-current={active ? 'page' : undefined}
                className={`group inline-flex min-h-10 items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold transition-[background-color,color,transform] duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring motion-safe:hover:-translate-y-px ${
                  active
                    ? 'bg-primary text-primary-foreground shadow-[0_2px_0_hsl(178_64%_18%)]'
                    : 'text-muted-foreground hover:bg-card hover:text-foreground'
                }`}
              >
                <Icon className="h-4 w-4 shrink-0" aria-hidden />
                <span>{label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

export function WorkspaceBrand() {
  return (
    <Link href="/workspace/dashboard" className="inline-flex shrink-0 items-center gap-2 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring" data-testid="link-workspace-home">
      <Mark className="h-7 w-7" />
      <span className="text-base font-bold tracking-tight">Jeeves</span>
    </Link>
  );
}
