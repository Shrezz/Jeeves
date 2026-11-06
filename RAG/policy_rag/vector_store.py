"""
vector_store.py
===============
All Chroma access lives here (Decisions D2, D8, D9).

1. One persistent collection holds every user's chunks.
2. Isolation is done with metadata filters: EVERY read is filtered by
   user_id AND policy_number (see access_filter). No function in this module
   reads chunks without that filter.
3. Re-ingesting a policy deletes that user's old chunks for the policy first,
   then inserts the new ones with deterministic ids, so there are never
   duplicates.
"""
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from . import config
from .tracing import trace_log, traced

_embeddings_override: Optional[Embeddings] = None   # tests can inject fake embeddings


def set_embeddings(embeddings: Embeddings) -> None:
    """Replace the embedding model (used only by offline tests)."""
    global _embeddings_override
    _embeddings_override = embeddings
    get_store.cache_clear()


@lru_cache(maxsize=1)
def get_store() -> Chroma:
    """Open (or create) the persistent Chroma collection once per process."""
    embeddings = _embeddings_override or OpenAIEmbeddings(model=config.EMBEDDING_MODEL)
    config.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return Chroma(collection_name=config.CHROMA_COLLECTION,
                  embedding_function=embeddings,
                  persist_directory=str(config.CHROMA_DIR),
                  collection_metadata={"hnsw:space": config.CHROMA_DISTANCE})


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
def access_filter(user_id: str, policy_number: str, extra: Optional[Dict] = None) -> Dict:
    """Chroma 'where' clause that limits results to one user's one policy."""
    clauses = [{"user_id": {"$eq": user_id}}, {"policy_number": {"$eq": policy_number}}]
    if extra:
        clauses += [{k: {"$eq": v}} for k, v in extra.items()]
    return {"$and": clauses}


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------
@traced
def replace_policy_chunks(user_id: str, policy_number: str, docs: List[Document]) -> bool:
    """Delete this user's existing chunks for the policy, then add the new ones.
    Returns True if older chunks existed (i.e. this was a re-ingest)."""
    store = get_store()
    existing = store.get(where=access_filter(user_id, policy_number), include=[])["ids"]
    if existing:
        store.delete(ids=existing)
    store.add_documents(docs, ids=[d.metadata["chunk_id"] for d in docs])
    trace_log("collection", config.CHROMA_COLLECTION)
    trace_log("deleted_old_chunks", len(existing))
    trace_log("inserted_chunks", len(docs))
    return bool(existing)


def delete_policy_chunks(user_id: str, policy_number: str) -> int:
    """Remove all chunks of a user's policy. Returns the number removed."""
    store = get_store()
    ids = store.get(where=access_filter(user_id, policy_number), include=[])["ids"]
    if ids:
        store.delete(ids=ids)
    return len(ids)


# ---------------------------------------------------------------------------
# Reads (always filtered)
# ---------------------------------------------------------------------------
def get_policy_chunks(user_id: str, policy_number: str, extra: Optional[Dict] = None) -> List[Document]:
    """Return stored chunks of one user's policy (optionally narrowed, e.g. chunk_type)."""
    res = get_store().get(where=access_filter(user_id, policy_number, extra), include=["documents", "metadatas"])
    docs = [Document(page_content=t, metadata=m) for t, m in zip(res["documents"], res["metadatas"])]
    return sorted(docs, key=lambda d: d.metadata.get("chunk_index", 0))


def count_policy_chunks(user_id: str, policy_number: str) -> int:
    return len(get_store().get(where=access_filter(user_id, policy_number), include=[])["ids"])


def embed_question(question: str) -> List[float]:
    """Embed the question once; the vector is reused by every search below."""
    return get_store().embeddings.embed_query(question)


def scored_candidates(vector: List[float], user_id: str, policy_number: str, k: int) -> List[Tuple[Document, float]]:
    """Top-k chunks by cosine distance (lower = closer) inside one policy."""
    return get_store().similarity_search_by_vector_with_relevance_scores(
        vector, k=k, filter=access_filter(user_id, policy_number))


def mmr_select(vector: List[float], user_id: str, policy_number: str, k: int, fetch_k: int) -> List[Document]:
    """Maximal Marginal Relevance: relevant but not repetitive chunks inside one policy."""
    return get_store().max_marginal_relevance_search_by_vector(
        vector, k=k, fetch_k=fetch_k, lambda_mult=config.MMR_LAMBDA,
        filter=access_filter(user_id, policy_number))
