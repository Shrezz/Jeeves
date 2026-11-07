import { useState } from 'react';
import { useListJeevConversations } from '@workspace/api-client-react';
import { MessageSquareText } from 'lucide-react';
import { Btn } from '@/components/cw';
import { JeevConversationWindow } from '@/components/jeev-conversation';

export function DashboardJeevChat() {
  const [active, setActive] = useState<{ id: string; saved: boolean } | null>(null);
  const [visible, setVisible] = useState(false);
  const history = useListJeevConversations({
    query: { staleTime: 10000, refetchOnWindowFocus: true },
  });
  const open = (id: string, saved: boolean) => { setActive({ id, saved }); setVisible(true); };
  return (
    <section aria-labelledby="chat-heading" data-testid="dashboard-section-chat" className="overflow-hidden rounded-2xl border border-card-border bg-card">
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-card-border p-5">
        <div className="flex min-w-0 flex-1 gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-secondary text-primary"><MessageSquareText className="h-5 w-5" aria-hidden /></span>
          <div>
            <h2 id="chat-heading" className="font-display text-xl">Chat with Jeeves</h2>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">Ask what your policy covers, prepare a claim, or update an existing one. You can check coverage without opening a claim.</p>
          </div>
        </div>
        <Btn onClick={() => open(crypto.randomUUID(), false)} data-testid="button-start-dashboard-chat" aria-expanded={visible} aria-controls={active ? 'dashboard-jeev-chat' : undefined}>Start a Chat</Btn>
      </header>
      <div className="space-y-4 p-5">
        {active && (
          <div hidden={!visible}>
            <JeevConversationWindow key={active.id} conversationId={active.id} saved={active.saved} onClose={() => setVisible(false)} />
          </div>
        )}
        {history.isLoading ? <p role="status" className="text-sm text-muted-foreground">Loading your conversations…</p>
          : history.isError ? <div role="alert"><p className="text-sm text-muted-foreground">Your conversations couldn’t load.</p><Btn variant="outline" className="mt-2" onClick={() => void history.refetch()}>Try again</Btn></div>
          : history.data?.length ? (
            <div className="space-y-3" aria-label="Previous conversations">
              {history.data.map((conversation) => (
                <article key={conversation.id} className="rounded-xl border border-card-border p-4">
                  <h3 className="break-words font-semibold">{conversation.title}</h3>
                  <p className="mt-1 text-xs text-muted-foreground">Last conversation {new Date(conversation.updatedAt).toLocaleDateString()}</p>
                  <Btn variant="ghost" className="mt-2" data-testid={`button-open-conversation-${conversation.id}`} onClick={() => open(conversation.id, true)}>Continue chat</Btn>
                </article>
              ))}
            </div>
          ) : !visible && <p data-testid="empty-chat" className="rounded-xl border border-dashed border-input bg-background p-4 text-sm leading-6 text-muted-foreground">Start a conversation with Jeeves. Your messages and replies are private and saved separately from claims.</p>}
      </div>
    </section>
  );
}
