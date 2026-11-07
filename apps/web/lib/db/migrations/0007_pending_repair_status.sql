ALTER TABLE public.claims DROP CONSTRAINT claims_repair_status_check;
ALTER TABLE public.claims ADD CONSTRAINT claims_repair_status_check
  CHECK (incident_json->>'repair_status' IS NULL OR incident_json->>'repair_status' IN ('unknown','pending','scheduled','completed'));
