-- App-visible projection of a run; LangGraph's private tables store resumable interrupts.
CREATE SCHEMA IF NOT EXISTS claim_graph;
ALTER TABLE claim_guidance ADD COLUMN workflow jsonb CHECK (jsonb_typeof(workflow) = 'object');
-- Executing an approved revision twice must never apply a status or generate another packet.
CREATE TABLE claim_workflow_commits (
    run_id uuid PRIMARY KEY REFERENCES claim_guidance(id) ON DELETE CASCADE,
    request_key text NOT NULL,
    result jsonb NOT NULL
);
