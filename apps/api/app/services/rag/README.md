# Policy RAG component

The package implements the policy text-to-evidence path:

1. Extract a text PDF one page at a time and preserve one-based page numbers.
2. Split by detected numbered section and create overlapping 600-token chunks by default.
3. Embed chunks through the injected `EmbeddingProvider` and store them through `PolicyChunkStore`.
4. Embed a question, retrieve within the selected user-owned policy, and return page/section citations.

## Integration still needed

Implement `EmbeddingProvider` for the team's chosen embedding model and `PolicyChunkStore` for Postgres/pgvector. Keep the embedding model and vector dimension consistent for ingestion and query. The store query must filter by both `user_id` and `policy_id`; derive `user_id` from the authenticated session. The repo was empty, so this component intentionally leaves model-vendor and database-driver choices to the team.

The MVP supports text PDFs. OCR for scans and real policy data are outside the current scope.
