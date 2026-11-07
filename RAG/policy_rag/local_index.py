"""Local UI retrieval: reuse the policy parser/chunker, with CPU embeddings and durable Chroma."""
from collections import defaultdict
from pathlib import Path
from uuid import UUID

import chromadb
from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

from .chunker import build_chunks
from .pdf_parser import parse_pdf
from .policy_identity import read_identity
from .observability import span


class LocalPolicyIndex:
    """Immutable UI policy UUIDs isolate uploads even when their printed numbers match."""

    def __init__(self, directory: Path, embed=None):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if embed is None:
            embed = ONNXMiniLM_L6_V2(preferred_providers=["CPUExecutionProvider"])
            embed.DOWNLOAD_PATH = directory / "model"
        self.embed = embed
        self.collection = chromadb.PersistentClient(path=str(directory / "chroma")).get_or_create_collection(
            "ui_policy_minilm_v1", embedding_function=None, metadata={"hnsw:space": "cosine"}
        )

    @staticmethod
    def scope(owner: str, policy: UUID) -> dict:
        return {"$and": [{"user_id": {"$eq": owner}}, {"policy_id": {"$eq": str(policy)}}]}

    def index(self, owner: str, policy: UUID, pdf: Path) -> int:
        with span("policy-pdf-extraction"):
            elements = parse_pdf(pdf)
        identity = read_identity(elements)
        by_page = defaultdict(list)
        for element in elements:
            by_page[element.page].append(element)
        chunks = []
        for page_elements in by_page.values():
            # Bound chunks to a physical page so a citation always opens the right page.
            chunks.extend(build_chunks(page_elements, {
                "user_id": owner, "policy_id": str(policy), "doc_version": "v1",
                "policy_number": identity.policy_number or "", "form": identity.form or "",
            }))
        if not chunks:
            raise ValueError("no_text")
        if len(chunks) > 2000:
            raise ValueError("too_large")
        for offset in range(0, len(chunks), 32):
            batch = chunks[offset:offset + 32]
            texts = [doc.page_content for doc in batch]
            ids = [f"{policy}:{offset+i}" for i in range(len(batch))]
            with span("policy-embedding", model="all-MiniLM-L6-v2", batch_size=len(texts)):
                embeddings = self.embed(texts)
            self.collection.upsert(ids=ids, documents=texts, embeddings=embeddings,
                metadatas=[{**doc.metadata, "chunk_id": cid} for doc, cid in zip(batch, ids)])
        count = len(self.collection.get(where=self.scope(owner, policy), include=[])["ids"])
        if count != len(chunks):
            raise RuntimeError("Stored chunk count does not match the document")
        return count

    def search(self, owner: str, policy: UUID, question: str, *, for_chat: bool = False) -> list[dict]:
        queries = [question]
        if for_chat:
            # The incident alone may retrieve only the coverage grant and miss terms that change it.
            queries += ["Covered causes exclusions conditions endorsements for " + question[:220],
                        "Declarations applicable deductible expense limit estimated payment endorsements"]
        with span("query-embedding", model="all-MiniLM-L6-v2", batch_size=len(queries)):
            embeddings = self.embed(queries)
        with span("vector-search", query_count=len(queries)):
            result = self.collection.query(query_embeddings=embeddings, n_results=6 if for_chat else 3,
            where=self.scope(owner, policy), include=["documents", "metadatas"])
        hits = {}
        for rank in range(max(map(len, result["ids"]), default=0)):
            for ids, metas, docs in zip(result["ids"], result["metadatas"], result["documents"]):
                if rank < len(ids):
                    cid, meta, text = ids[rank], metas[rank], docs[rank]
                    hits[cid] = {"chunkId": cid, "page": meta["page"], "section": meta["heading_path"],
                                 "excerpt": text.partition("\n")[2] or text}
        return list(hits.values())[:10]
