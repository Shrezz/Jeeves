-- Run through app.db.migrate with this directory, after the UI baseline.
-- The runner applies the batch transactionally and records checksums.
DO $$
BEGIN
  IF to_regclass('public.users') IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM information_schema.columns WHERE table_schema='public'
    AND table_name='users' AND column_name='id' AND data_type='text'
  ) THEN
    RAISE EXCEPTION 'Existing users are not Clerk IDs; an explicit identity backfill is required';
  END IF;
  IF EXISTS (SELECT owner_id FROM public.policies WHERE owner_id !~ '^user_[A-Za-z0-9_]+$'
             UNION ALL SELECT owner_id FROM public.claims WHERE owner_id !~ '^user_[A-Za-z0-9_]+$') THEN
    RAISE EXCEPTION 'Unmapped owner IDs found; do not infer Clerk identity from email';
  END IF;
  IF EXISTS (SELECT 1 FROM public.claims WHERE status IN ('Package prepared','prepared','filed_demo','resolved')) THEN
    RAISE EXCEPTION 'Prepared, simulated filing, or ambiguous resolution requires explicit reconciliation before migration';
  END IF;
  IF EXISTS (SELECT 1 FROM public.claims WHERE status NOT IN (
    'Draft','Gathering evidence','Preparation requested','Filed by me with insurer',
    'Insurer decision received','Resolved without filing',
    'draft','gathering_evidence','preparation_requested','filed_by_user',
    'insurer_decision_received','resolved_without_filing')) THEN
    RAISE EXCEPTION 'Unknown claim lifecycle value; reconcile it instead of guessing';
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.users (
  id text PRIMARY KEY,
  name text,
  email text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT users_clerk_subject_check CHECK (id ~ '^user_[A-Za-z0-9_]+$')
);
INSERT INTO public.users(id)
  SELECT owner_id FROM public.policies UNION SELECT owner_id FROM public.claims
  ON CONFLICT (id) DO NOTHING;

ALTER TABLE public.policies ADD CONSTRAINT policies_owner_id_users_id_fk
  FOREIGN KEY (owner_id) REFERENCES public.users(id);
ALTER TABLE public.claims ADD CONSTRAINT claims_owner_id_users_id_fk
  FOREIGN KEY (owner_id) REFERENCES public.users(id);

UPDATE public.claims SET status = CASE status
  WHEN 'Draft' THEN 'draft'
  WHEN 'Gathering evidence' THEN 'gathering_evidence'
  WHEN 'Preparation requested' THEN 'preparation_requested'
  WHEN 'Filed by me with insurer' THEN 'filed_by_user'
  WHEN 'Insurer decision received' THEN 'insurer_decision_received'
  WHEN 'Resolved without filing' THEN 'resolved_without_filing'
  ELSE status END;
-- Preserve historical message wording/status labels; they are an audit record.
ALTER TABLE public.claims ALTER COLUMN status SET DEFAULT 'draft';
ALTER TABLE public.claims ADD CONSTRAINT claims_status_check CHECK (status IN (
  'draft','gathering_evidence','preparation_requested','prepared','filed_by_user',
  'insurer_decision_received','resolved_without_filing'
));
ALTER TABLE public.claims ADD COLUMN incident_json jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE public.claims ADD COLUMN insurer_outcome text NOT NULL DEFAULT 'unknown';
ALTER TABLE public.claims ADD COLUMN insurer_outcome_source text;
UPDATE public.claims SET insurer_outcome_source='user_reported'
  WHERE status='insurer_decision_received';
ALTER TABLE public.claims ADD CONSTRAINT claims_incident_object_check
  CHECK (jsonb_typeof(incident_json)='object');
ALTER TABLE public.claims ADD CONSTRAINT claims_repair_status_check
  CHECK (incident_json->>'repair_status' IS NULL OR incident_json->>'repair_status' IN ('unknown','scheduled','completed'));
ALTER TABLE public.claims ADD CONSTRAINT claims_insurer_outcome_check
  CHECK (insurer_outcome IN ('unknown','approved','partially_approved','denied'));
ALTER TABLE public.claims ADD CONSTRAINT claims_insurer_source_check CHECK (
  (insurer_outcome_source IS NULL OR insurer_outcome_source='user_reported') AND
  (insurer_outcome='unknown' OR insurer_outcome_source IS NOT NULL)
);
