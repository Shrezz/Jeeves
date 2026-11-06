"""Bridge the existing synchronous RAG service to the async agent tool contract."""

import asyncio
from dataclasses import dataclass

from app.services.rag.retrieval import retrieve_policy_evidence
from app.services.rag.types import Citation, EmbeddingProvider, PolicyChunkStore


@dataclass(frozen=True)
class PolicyRagAdapter:
    embedder: EmbeddingProvider
    store: PolicyChunkStore

    async def retrieve_evidence(
        self, *, user_id: str, policy_id: str, question: str, limit: int
    ) -> list[Citation]:
        # Avoid the helper's short default excerpt. Store queries must still enforce
        # ownership and policy-version selection; agents reject mismatched versions.
        return await asyncio.to_thread(
            retrieve_policy_evidence,
            question,
            user_id=user_id,
            policy_id=policy_id,
            embedder=self.embedder,
            store=self.store,
            limit=limit,
            max_excerpt_chars=12000,
        )
