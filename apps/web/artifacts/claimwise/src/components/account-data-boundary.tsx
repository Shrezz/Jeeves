import { useEffect, useState, type ReactNode } from 'react';
import { useUser } from '@clerk/react';
import { QueryClientProvider } from '@tanstack/react-query';
import { createAccountQueryClient } from '@/lib/queryClient';
import { setClaimDraftOwner } from '@/pages/claim-workspace';

function AccountScope({ ownerId, children }: { ownerId: string | null; children: ReactNode }) {
  const [client] = useState(createAccountQueryClient);
  // A fresh scope also distinguishes A -> B -> A while A's old requests are
  // still finishing. Their callbacks retain only the discarded cache/scope.
  const [draftScope] = useState(() => crypto.randomUUID());
  setClaimDraftOwner(ownerId ? draftScope : null);

  useEffect(() => () => {
    void client.cancelQueries();
    client.clear();
  }, [client]);

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

export default function AccountDataBoundary({ children }: { children: ReactNode }) {
  const { isLoaded, user } = useUser();
  if (!isLoaded) return <div role="status" className="p-6 text-sm text-muted-foreground">Loading your session…</div>;
  const ownerId = user?.id ?? null;
  return <AccountScope key={ownerId ?? 'signed-out'} ownerId={ownerId}>{children}</AccountScope>;
}
