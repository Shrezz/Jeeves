"""Exercise policy PDF ingestion and owner-scoped retrieval without a database."""

import asyncio
from dataclasses import replace

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.services.rag.chunking import chunk_policy_pages
from app.services.rag.ingestion import _embed_chunks, extract_pdf_pages, ingest_policy_pdf
from app.services.rag.retrieval import retrieve_policy_evidence
from app.services.rag.types import PolicyChunk, PolicyPage
from app.services.rag_adapter import PolicyRagAdapter


class CharacterEncoding:
    def encode(self, value):
        return list(value)

    def decode(self, value):
        return "".join(value)


class SyntheticEmbeddings:
    def embed(self, texts):
        return [(float(len(text)), 1.0, 2.0) for text in texts]


class MemoryChunks:
    def __init__(self):
        self.chunks = []
        self.calls = []

    def upsert(self, chunks):
        self.chunks = list(chunks)

    def search(self, *, user_id, policy_id, query_embedding, limit):
        self.calls.append((user_id, policy_id))
        return [
            (chunk, 0.9)
            for chunk in self.chunks
            if (chunk.user_id, chunk.policy_id) == (user_id, policy_id)
        ][:limit]


def write_text_pdf(path):
    writer = PdfWriter()
    for heading, body in (
        ("1. Coverage", "Windborne debris damage is covered."),
        ("2. Exclusion", "Wear and tear is excluded."),
    ):
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        contents = DecodedStreamObject()
        contents.set_data(f"BT /F1 12 Tf 72 700 Td ({heading}) Tj 0 -20 Td ({body}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(contents)
    writer.write(path)


def test_pdf_to_owner_scoped_citations(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.rag.chunking.tiktoken.get_encoding", lambda _: CharacterEncoding()
    )
    path = tmp_path / "synthetic-policy.pdf"
    write_text_pdf(path)
    pages = extract_pdf_pages(path)
    assert [page.page for page in pages] == [1, 2]
    assert "Windborne" in pages[0].text
    store = MemoryChunks()
    count = ingest_policy_pdf(
        path,
        user_id="owner",
        policy_id="policy",
        policy_version="1",
        embedder=SyntheticEmbeddings(),
        store=store,
        max_tokens=60,
        overlap_tokens=5,
    )
    assert count == 2
    assert [chunk.section for chunk in store.chunks] == ["1. Coverage", "2. Exclusion"]
    assert all(len(chunk.embedding) == 3 for chunk in store.chunks)
    evidence = retrieve_policy_evidence(
        "What is covered?",
        user_id="owner",
        policy_id="policy",
        embedder=SyntheticEmbeddings(),
        store=store,
    )
    assert [item.page for item in evidence] == [1, 2]
    assert evidence[0].section == "1. Coverage"
    assert evidence[0].policy_version == "1"
    assert (
        retrieve_policy_evidence(
            "What is covered?",
            user_id="other",
            policy_id="policy",
            embedder=SyntheticEmbeddings(),
            store=store,
        )
        == []
    )
    adapter = PolicyRagAdapter(SyntheticEmbeddings(), store)
    async_result = asyncio.run(
        adapter.retrieve_evidence(
            user_id="owner", policy_id="policy", question="What is covered?", limit=1
        )
    )
    assert len(async_result) == 1 and async_result[0].chunk_id == evidence[0].chunk_id
    assert store.calls[-1] == ("owner", "policy")


def test_wrong_owner_or_policy_from_store_is_rejected():
    chunk = PolicyChunk(
        id="chunk",
        user_id="another-user",
        policy_id="policy",
        policy_version="1",
        page=1,
        section="1",
        content="synthetic",
        embedding=(1.0,),
    )

    class BuggyStore:
        def search(self, **kwargs):
            return [(chunk, 0.8)]

    with pytest.raises(ValueError, match="selected owner and policy"):
        retrieve_policy_evidence(
            "coverage?",
            user_id="owner",
            policy_id="policy",
            embedder=SyntheticEmbeddings(),
            store=BuggyStore(),
        )
    chunk = replace(chunk, user_id="owner", policy_id="another-policy")
    with pytest.raises(ValueError, match="selected owner and policy"):
        retrieve_policy_evidence(
            "coverage?",
            user_id="owner",
            policy_id="policy",
            embedder=SyntheticEmbeddings(),
            store=BuggyStore(),
        )


def test_pdf_without_extractable_text_is_rejected(tmp_path):
    path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(path)
    with pytest.raises(ValueError, match="no extractable text"):
        extract_pdf_pages(path)


def test_chunk_overlap_and_stable_ids(monkeypatch):
    monkeypatch.setattr(
        "app.services.rag.chunking.tiktoken.get_encoding", lambda _: CharacterEncoding()
    )
    pages = [PolicyPage(page=1, text="1. Section\nabcdefghijklmnop")]
    kwargs = {
        "user_id": "u",
        "policy_id": "p",
        "policy_version": "1",
        "max_tokens": 8,
        "overlap_tokens": 2,
    }
    first = chunk_policy_pages(pages, **kwargs)
    second = chunk_policy_pages(pages, **kwargs)
    assert [chunk.content for chunk in first] == ["abcdefgh", "ghijklmn", "mnop"]
    assert [chunk.id for chunk in first] == [chunk.id for chunk in second]
    with pytest.raises(ValueError, match="overlap_tokens"):
        chunk_policy_pages(pages, **(kwargs | {"overlap_tokens": 8}))


@pytest.mark.parametrize("vectors", [[], [()], [(1.0,), (1.0, 2.0)]])
def test_invalid_embedding_batches_fail_before_storage(vectors):
    chunk = PolicyChunk(
        id="c",
        user_id="u",
        policy_id="p",
        policy_version="1",
        page=1,
        section=None,
        content="synthetic",
        embedding=(),
    )

    class BadEmbeddings:
        def embed(self, texts):
            return vectors

    chunks = [chunk, replace(chunk, id="c2")] if len(vectors) == 2 else [chunk]
    with pytest.raises(ValueError):
        _embed_chunks(chunks, BadEmbeddings(), batch_size=2)
