"""Extract, chunk, embed, and persist a text-based policy PDF."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Sequence

from pypdf import PdfReader

from .chunking import chunk_policy_pages
from .types import EmbeddingProvider, PolicyChunk, PolicyChunkStore, PolicyPage


def extract_pdf_pages(pdf_path: str | Path) -> list[PolicyPage]:
    """Extract text with one-based PDF page numbers; scanned PDFs are unsupported."""
    reader = PdfReader(str(pdf_path))
    pages = [
        PolicyPage(page=index, text=pdf_page.extract_text() or "")
        for index, pdf_page in enumerate(reader.pages, start=1)
    ]
    if not any(page.text.strip() for page in pages):
        raise ValueError("The PDF contains no extractable text; scanned PDFs are unsupported")
    return pages


def _embed_chunks(
    chunks: Sequence[PolicyChunk],
    embedder: EmbeddingProvider,
    *,
    batch_size: int,
) -> list[PolicyChunk]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    embedded: list[PolicyChunk] = []
    expected_dimension: int | None = None
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        vectors = embedder.embed([chunk.content for chunk in batch])
        if len(vectors) != len(batch):
            raise ValueError("Embedding provider returned a different number of vectors than inputs")
        for chunk, vector in zip(batch, vectors, strict=True):
            if not vector:
                raise ValueError("Embedding provider returned an empty vector")
            if expected_dimension is None:
                expected_dimension = len(vector)
            if len(vector) != expected_dimension:
                raise ValueError("Embedding provider returned inconsistent vector dimensions")
            embedded.append(replace(chunk, embedding=tuple(float(value) for value in vector)))
    return embedded


def ingest_policy_pdf(
    pdf_path: str | Path,
    *,
    user_id: str,
    policy_id: str,
    policy_version: str,
    embedder: EmbeddingProvider,
    store: PolicyChunkStore,
    max_tokens: int = 600,
    overlap_tokens: int = 60,
    batch_size: int = 64,
) -> int:
    """Ingest a policy PDF and return the number of stored chunks."""
    pages = extract_pdf_pages(pdf_path)
    chunks = chunk_policy_pages(
        pages,
        user_id=user_id,
        policy_id=policy_id,
        policy_version=policy_version,
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens,
    )
    if not chunks:
        raise ValueError("No policy text chunks were produced")
    store.upsert(_embed_chunks(chunks, embedder, batch_size=batch_size))
    return len(chunks)
