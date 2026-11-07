-- Add the review and independent Jeev chat tables from the dashboard branch.
-- A local Claimwise submission is not an insurer filing.
ALTER TABLE public.claims DROP CONSTRAINT claims_status_check;
ALTER TABLE public.claims ADD CONSTRAINT claims_status_check CHECK (status IN (
  'draft', 'gathering_evidence', 'preparation_requested', 'prepared',
  'filed_by_user', 'insurer_decision_received', 'resolved_without_filing',
  'submitted_in_claimwise'
));

CREATE TABLE IF NOT EXISTS public.claim_reviews (
  claim_id uuid PRIMARY KEY REFERENCES public.claims(id) ON DELETE CASCADE,
  comments text NOT NULL DEFAULT '', version integer NOT NULL DEFAULT 0,
  submitted_at timestamptz, snapshot jsonb,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.jeev_conversations (
  id uuid PRIMARY KEY, owner_id text NOT NULL, title text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS jeev_conversations_owner_idx ON public.jeev_conversations(owner_id);
CREATE TABLE IF NOT EXISTS public.jeev_messages (
  id uuid PRIMARY KEY,
  conversation_id uuid NOT NULL REFERENCES public.jeev_conversations(id) ON DELETE CASCADE,
  content text NOT NULL, reply text, reply_state text NOT NULL DEFAULT 'pending',
  lease_id uuid NOT NULL, attempts integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS jeev_messages_conversation_idx ON public.jeev_messages(conversation_id);
