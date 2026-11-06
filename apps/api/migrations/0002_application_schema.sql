-- Claim Companion MVP: six application tables. Synthetic demo data only.
-- Forward-only migration; the runner applies the complete pending batch atomically.
-- vector(1536) is the schema contract, not an implemented embedding provider.

CREATE FUNCTION public.set_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at = clock_timestamp();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE public.users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL CHECK (btrim(name) <> ''),
  email text NOT NULL CHECK (btrim(email) <> '' AND email = btrim(email)),
  password_hash text NOT NULL CHECK (btrim(password_hash) <> ''),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX users_email_lower_key ON public.users (lower(email));

CREATE TABLE public.policies (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  label text NOT NULL CHECK (btrim(label) <> ''),
  file_path text NOT NULL CHECK (btrim(file_path) <> ''),
  version integer NOT NULL DEFAULT 1 CHECK (version > 0),
  deductible numeric(12,2),
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(metadata_json) = 'object'),
  ingestion_status text NOT NULL DEFAULT 'parsing',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT policies_ingestion_status_check
    CHECK (ingestion_status IN ('parsing', 'ready', 'error')),
  CONSTRAINT policies_deductible_check
    CHECK (deductible IS NULL OR (deductible >= 0 AND deductible < 'Infinity'::numeric)),
  CONSTRAINT policies_id_user_key UNIQUE (id, user_id),
  CONSTRAINT policies_user_version_key UNIQUE (user_id, version)
);
CREATE TRIGGER trg_policies_updated BEFORE UPDATE ON public.policies
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TABLE public.policy_chunks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  policy_id uuid NOT NULL REFERENCES public.policies(id) ON DELETE CASCADE,
  page integer NOT NULL CHECK (page > 0),
  section text,
  content text NOT NULL CHECK (btrim(content) <> ''),
  embedding vector(1536) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
-- Exact, owner/policy-filtered search is sufficient for the small synthetic corpus.
CREATE INDEX idx_chunks_policy ON public.policy_chunks(policy_id);

CREATE TABLE public.claims (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  claim_number text GENERATED ALWAYS AS
    ('CC-CLM-' || upper(substr(id::text, 1, 8))) STORED UNIQUE,
  user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  policy_id uuid NOT NULL,
  title text NOT NULL CHECK (btrim(title) <> ''),
  incident_json jsonb NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(incident_json) = 'object'),
  assessment_json jsonb NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(assessment_json) = 'object'),
  package_json jsonb NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(package_json) = 'object'),
  status text NOT NULL DEFAULT 'draft',
  version integer NOT NULL DEFAULT 1 CHECK (version > 0),
  approved_version integer,
  packet_path text CHECK (packet_path IS NULL OR btrim(packet_path) <> ''),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT claims_status_check CHECK (status IN
    ('draft', 'needs_info', 'awaiting_review', 'prepared',
     'resolved_without_filing', 'filed_demo', 'action_failed')),
  CONSTRAINT claims_approval_version_check
    CHECK (approved_version IS NULL OR approved_version = version),
  CONSTRAINT claims_final_approval_check CHECK (
    status NOT IN ('prepared', 'resolved_without_filing', 'filed_demo') OR
    (approved_version IS NOT NULL AND approved_version = version)),
  CONSTRAINT claims_prepared_packet_check CHECK (
    status <> 'prepared' OR (packet_path IS NOT NULL AND btrim(packet_path) <> '')),
  CONSTRAINT claims_packet_approval_check CHECK (
    packet_path IS NULL OR (approved_version IS NOT NULL AND approved_version = version)),
  CONSTRAINT claims_policy_owner_fk FOREIGN KEY (policy_id, user_id)
    REFERENCES public.policies(id, user_id),
  CONSTRAINT claims_id_user_key UNIQUE (id, user_id)
);
CREATE INDEX idx_claims_user_updated ON public.claims(user_id, updated_at DESC);
CREATE INDEX idx_claims_policy ON public.claims(policy_id);
CREATE TRIGGER trg_claims_updated BEFORE UPDATE ON public.claims
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- Once a package exists, changing its facts requires a new, unapproved draft.
-- This rejects unsafe writes rather than silently treating them as approved.
-- Conservative: changes to any package field also require renewed review.
CREATE FUNCTION public.guard_claim_revision() RETURNS trigger AS $$
BEGIN
  IF NEW.id IS DISTINCT FROM OLD.id OR NEW.user_id IS DISTINCT FROM OLD.user_id THEN
    RAISE EXCEPTION 'Claim identity and ownership cannot change' USING ERRCODE = '23514';
  END IF;
  IF NEW.version < OLD.version OR NEW.version > OLD.version + 1 THEN
    RAISE EXCEPTION 'Claim version must stay current or advance by one' USING ERRCODE = '23514';
  END IF;
  IF ((OLD.package_json <> '{}'::jsonb OR OLD.approved_version IS NOT NULL) AND
      ROW(NEW.policy_id, NEW.incident_json, NEW.assessment_json, NEW.package_json)
      IS DISTINCT FROM
      ROW(OLD.policy_id, OLD.incident_json, OLD.assessment_json, OLD.package_json))
      OR NEW.version <> OLD.version THEN
    IF NEW.version <> OLD.version + 1 OR NEW.approved_version IS NOT NULL
       OR NEW.packet_path IS NOT NULL OR NEW.status <> 'draft' THEN
      RAISE EXCEPTION 'Package edits require the next version, draft status, and cleared approval/packet'
        USING ERRCODE = '23514';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_claims_revision BEFORE UPDATE ON public.claims
  FOR EACH ROW EXECUTE FUNCTION public.guard_claim_revision();

CREATE TABLE public.messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  seq bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
  user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  conversation_id uuid NOT NULL,
  claim_id uuid,
  role text NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
  content text NOT NULL,
  attachment_path text,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT messages_claim_owner_fk FOREIGN KEY (claim_id, user_id)
    REFERENCES public.claims(id, user_id) ON DELETE CASCADE
);
CREATE INDEX idx_messages_conversation ON public.messages(user_id, conversation_id, seq);
CREATE INDEX idx_messages_claim ON public.messages(claim_id, seq);

CREATE TABLE public.claim_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  seq bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
  claim_id uuid NOT NULL REFERENCES public.claims(id) ON DELETE CASCADE,
  actor_user_id uuid REFERENCES public.users(id),
  event_type text NOT NULL CHECK (btrim(event_type) <> ''),
  details_json jsonb NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(details_json) = 'object'),
  request_key text UNIQUE CHECK (request_key IS NULL OR btrim(request_key) <> ''),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  -- A NULL actor denotes a backend/system event; non-NULL actors must own the claim.
  CONSTRAINT events_claim_owner_fk FOREIGN KEY (claim_id, actor_user_id)
    REFERENCES public.claims(id, user_id) ON DELETE CASCADE
);
CREATE INDEX idx_events_claim ON public.claim_events(claim_id, seq);
