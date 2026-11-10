"""Retrieve policy evidence scoped to the authenticated owner and policy."""

from __future__ import annotations

from ...observability.tracing import observation
from .types import Citation, EmbeddingProvider, PolicyChunkStore


def retrieve_policy_evidence(
    question: str,
    *,
    user_id: str,
    policy_id: str,
    embedder: EmbeddingProvider,
    store: PolicyChunkStore,
    limit: int = 5,
    max_excerpt_chars: int = 500,
) -> list[Citation]:
    """Return ranked passages with page/section citations.

    Resolve `user_id` from the authenticated session. The store must enforce
    both owner and policy filters in its database query.
    """
    if not question.strip():
        raise ValueError("question must not be empty")
    if limit <= 0 or max_excerpt_chars <= 0:
        raise ValueError("limit and max_excerpt_chars must be positive")

    with observation("policy-retrieval", input={"limit": limit}) as span:
        with observation("query-embedding", as_type="embedding"):
            vectors = embedder.embed([question.strip()])
            if len(vectors) != 1 or not vectors[0]:
                raise ValueError("Embedding provider did not return one query vector")
        with observation("vector-search", as_type="retriever"):
            results = store.search(
                user_id=user_id,
                policy_id=policy_id,
                query_embedding=vectors[0],
                limit=limit,
            )
            if any(
                chunk.user_id != user_id or chunk.policy_id != policy_id for chunk, _ in results
            ):
                raise ValueError(
                    "Retrieved evidence does not belong to the selected owner and policy"
                )
        span.update(output={"chunk_ids": [chunk.id for chunk, _ in results], "count": len(results)})
    return [
        Citation(
            chunk_id=chunk.id,
            policy_id=chunk.policy_id,
            policy_version=chunk.policy_version,
            page=chunk.page,
            section=chunk.section,
            excerpt=chunk.content[:max_excerpt_chars],
            score=float(score),
        )
        for chunk, score in results
    ]
