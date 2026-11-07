-- A dashboard turn may consult a policy without opening a claim.
ALTER TABLE public.jeev_messages
  ADD COLUMN policy_id uuid REFERENCES public.policies(id),
  ADD COLUMN route text CHECK (route IN ('answer_claim', 'file_claim', 'save_claim_status', 'clarify')),
  ADD COLUMN sources jsonb NOT NULL DEFAULT '[]'::jsonb;
