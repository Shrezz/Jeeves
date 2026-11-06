# API contracts

Agree on request and response field names before parallel UI, backend, agent, and evaluation work. The initial RAG boundary is defined in `apps/api/app/services/rag/types.py`:

- ingestion receives a policy ID, owner user ID, policy version, and PDF path;
- retrieval receives the authenticated user ID, selected policy ID, question, and result limit;
- returned evidence includes chunk ID, policy version, page, section, excerpt, and similarity score.

The storage adapter must scope retrieval by both user and policy. Resolve the user ID from the authenticated session; do not trust a browser-supplied owner ID.
