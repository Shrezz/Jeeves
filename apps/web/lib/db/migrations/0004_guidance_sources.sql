-- Keep quotes with the reviewed response; existing replies have no verified sources.
ALTER TABLE claim_guidance ADD COLUMN sources jsonb NOT NULL DEFAULT '[]'::jsonb
    CHECK (jsonb_typeof(sources) = 'array');
