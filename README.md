# Claim Companion

MVP workspace for a synthetic homeowners insurance claim assistant.

## Layout

- `apps/web/` — user interface.
- `apps/api/` — API, workflow, and policy RAG service.
- `packages/contracts/` — shared API contracts.
- `evals/` — synthetic scenarios and evaluation runner.
- `data/fixtures/` — fictional demo policy materials only.
- `docs/` — architecture and team contracts.

The GitHub repository was empty when cloned. This is the initial scaffold; app integrations remain to be added.

## RAG core

The API includes page-aware policy PDF extraction and chunking, with injected interfaces for embeddings and pgvector storage. See `apps/api/app/services/rag/README.md`.
