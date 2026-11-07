-- Establish the existing UI schema without replacing existing tables or data.
-- Refuse the incompatible, UUID-user Python prototype schema.
DO $$
BEGIN
  IF (to_regclass('public.policies') IS NOT NULL AND NOT EXISTS (
      SELECT 1 FROM information_schema.columns WHERE table_schema='public'
      AND table_name='policies' AND column_name='owner_id' AND data_type='text'))
    OR (to_regclass('public.claims') IS NOT NULL AND NOT EXISTS (
      SELECT 1 FROM information_schema.columns WHERE table_schema='public'
      AND table_name='claims' AND column_name='owner_id' AND data_type='text')) THEN
    RAISE EXCEPTION 'Expected the UI schema with Clerk owner_id; reconcile the prototype schema first';
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.policies (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id text NOT NULL,
  file_name text NOT NULL,
  size integer NOT NULL,
  object_path text NOT NULL,
  label text NOT NULL,
  deductible numeric(12,2),
  status text NOT NULL DEFAULT 'pending',
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT policies_id_owner_unique UNIQUE (id, owner_id)
);
CREATE INDEX IF NOT EXISTS policies_owner_status_idx ON public.policies(owner_id, status);

CREATE TABLE IF NOT EXISTS public.claims (
  id uuid PRIMARY KEY,
  owner_id text NOT NULL,
  policy_id uuid REFERENCES public.policies(id),
  title text NOT NULL,
  status text NOT NULL DEFAULT 'Draft',
  total_expenses numeric(16,2) NOT NULL DEFAULT 0,
  latest_update text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT claims_owned_policy_fk FOREIGN KEY (policy_id, owner_id)
    REFERENCES public.policies(id, owner_id)
);
CREATE INDEX IF NOT EXISTS claims_owner_updated_idx ON public.claims(owner_id, updated_at);

CREATE TABLE IF NOT EXISTS public.claim_messages (
  id uuid PRIMARY KEY,
  claim_id uuid NOT NULL REFERENCES public.claims(id) ON DELETE CASCADE,
  content text NOT NULL,
  kind text NOT NULL,
  expense numeric(12,2),
  status text,
  processing_status text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT claim_messages_claim_id_unique UNIQUE (claim_id, id)
);
CREATE INDEX IF NOT EXISTS claim_messages_claim_created_idx ON public.claim_messages(claim_id, created_at);

CREATE TABLE IF NOT EXISTS public.claim_evidence (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  claim_id uuid NOT NULL REFERENCES public.claims(id) ON DELETE CASCADE,
  message_id uuid REFERENCES public.claim_messages(id),
  file_name text NOT NULL,
  content_type text NOT NULL,
  size integer NOT NULL,
  object_path text NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT evidence_message_same_claim_fk FOREIGN KEY (claim_id, message_id)
    REFERENCES public.claim_messages(claim_id, id)
);
CREATE INDEX IF NOT EXISTS claim_evidence_claim_status_idx ON public.claim_evidence(claim_id, status);

CREATE TABLE IF NOT EXISTS public.claim_guidance (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  claim_id uuid NOT NULL REFERENCES public.claims(id) ON DELETE CASCADE,
  message_id uuid NOT NULL UNIQUE REFERENCES public.claim_messages(id) ON DELETE CASCADE,
  content text,
  state text NOT NULL DEFAULT 'pending',
  lease_id uuid NOT NULL,
  attempts integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT guidance_message_same_claim_fk FOREIGN KEY (claim_id, message_id)
    REFERENCES public.claim_messages(claim_id, id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS claim_guidance_claim_idx ON public.claim_guidance(claim_id);
