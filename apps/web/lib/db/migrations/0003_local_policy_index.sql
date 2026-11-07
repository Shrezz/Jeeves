-- Policy originals reside in the local database, separate from metadata-only list queries.
CREATE TABLE policy_documents (
    policy_id uuid PRIMARY KEY REFERENCES policies(id) ON DELETE CASCADE,
    content bytea NOT NULL CHECK (octet_length(content) BETWEEN 1 AND 20971520)
);
ALTER TABLE policies
    ADD COLUMN ingestion_status text NOT NULL DEFAULT 'not_started'
        CHECK (ingestion_status IN ('not_started','processing','ready','failed')),
    ADD COLUMN indexed_chunks integer NOT NULL DEFAULT 0,
    ADD CONSTRAINT policies_index_count_check CHECK (
        (ingestion_status='ready' AND indexed_chunks>0) OR
        (ingestion_status<>'ready' AND indexed_chunks=0)
    );
