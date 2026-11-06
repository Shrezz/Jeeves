"""Typed boundaries for policy ingestion, embeddings, storage, and evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class PolicyPage:
    page: int
    text: str


@dataclass(frozen=True)
class PolicyChunk:
    id: str
    user_id: str
    policy_id: str
    policy_version: str
    page: int
    section: str | None
    content: str
    embedding: Sequence[float]


@dataclass(frozen=True)
class Citation:
    chunk_id: str
    policy_id: str
    policy_version: str
    page: int
    section: str | None
    excerpt: str
    score: float


class EmbeddingProvider(Protocol):
    """Adapter for the team's selected embedding model."""

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return one same-dimension vector per input text."""


class PolicyChunkStore(Protocol):
    """Persistence boundary; the MVP adapter is intended to use pgvector."""

    def upsert(self, chunks: Sequence[PolicyChunk]) -> None:
        """Insert or replace chunks using their stable IDs."""

    def search(
        self,
        *,
        user_id: str,
        policy_id: str,
        query_embedding: Sequence[float],
        limit: int,
    ) -> Sequence[tuple[PolicyChunk, float]]:
        """Return nearest chunks scoped to both owner and selected policy."""
