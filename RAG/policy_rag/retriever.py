"""
retriever.py
============
Finds the chunks the LLM needs for one question (Decisions D4, D5, D6).

Pipeline
--------
1. Scope:   only the requesting user's policy (filter in vector_store).
2. Embed:   the question is embedded ONCE and the vector reused.
3. Search:  dense MMR, k = config.TOP_K from config.FETCH_K candidates.
            If config.HYBRID_ENABLED, dense and BM25 rankings are combined
            with weighted Reciprocal Rank Fusion instead.
4. Pin:     the policy's Declarations chunks are always added, because
            limits and deductibles live there and almost every payout
            question needs them.
5. Order:   pinned chunks first, then retrieved chunks; duplicates removed.

Trace details logged (v2): candidate pool with cosine distances, which
candidates were selected, BM25 and fusion scores (hybrid), pinned chunks,
and the final ordered list.
"""
import re
from typing import Dict, List, Tuple

from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from . import config
from . import vector_store as vs
from .tracing import chunk_summary, trace_log, traced

_TOKEN = re.compile(r"[a-z0-9$%][a-z0-9$%,.\-]*")
_bm25_cache: Dict[tuple, tuple] = {}     # (user_id, policy_number) -> (BM25Okapi, docs)


def _tokenize(text: str) -> List[str]:
    return [t.strip(".,") for t in _TOKEN.findall(text.lower())]


def clear_cache(user_id: str = None, policy_number: str = None) -> None:
    """Forget BM25 indexes (called after ingest/delete so they are rebuilt)."""
    if user_id is None:
        _bm25_cache.clear()
    else:
        _bm25_cache.pop((user_id, policy_number), None)


# ---------------------------------------------------------------------------
# Search strategies (each is a traced step)
# ---------------------------------------------------------------------------
@traced
def dense_candidates(vector: List[float], user_id: str, policy_number: str) -> List[Tuple[Document, float]]:
    """Candidate pool ranked by cosine distance (lower = closer)."""
    pool = vs.scored_candidates(vector, user_id, policy_number, config.FETCH_K)
    trace_log("score_meaning", "cosine distance, lower = closer")
    trace_log("candidate_pool", [chunk_summary(d, include_text=False, score=s, rank=i)
                                 for i, (d, s) in enumerate(pool, 1)])
    return pool


@traced
def mmr_search(vector: List[float], user_id: str, policy_number: str, pool: List[Tuple[Document, float]]) -> List[Document]:
    """Pick TOP_K relevant but diverse chunks from the pool."""
    picked = vs.mmr_select(vector, user_id, policy_number, config.TOP_K, config.FETCH_K)
    distance = {d.metadata["chunk_id"]: s for d, s in pool}
    trace_log("score_meaning", "cosine distance from candidate pool, lower = closer")
    trace_log("selected", [chunk_summary(d, include_text=False, score=distance.get(d.metadata["chunk_id"]), mmr_order=i)
                           for i, d in enumerate(picked, 1)])
    return picked


@traced
def bm25_rank(question: str, user_id: str, policy_number: str, k: int) -> List[Document]:
    """Keyword ranking over the policy's chunks. Index is built once per policy."""
    key = (user_id, policy_number)
    built = key not in _bm25_cache
    if built:
        docs = vs.get_policy_chunks(user_id, policy_number)
        _bm25_cache[key] = (BM25Okapi([_tokenize(d.page_content) for d in docs]), docs)
    index, docs = _bm25_cache[key]
    scores = index.get_scores(_tokenize(question))
    ranked = [i for i in sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)[:k] if scores[i] > 0]
    trace_log("index_built_now", built)
    trace_log("query_tokens", _tokenize(question))
    trace_log("score_meaning", "BM25 score, higher = better")
    trace_log("bm25_ranking", [chunk_summary(docs[i], include_text=False, score=scores[i], rank=r)
                               for r, i in enumerate(ranked, 1)])
    return [docs[i] for i in ranked]


@traced
def rrf_fuse(dense: List[Document], keyword: List[Document]) -> List[Document]:
    """Weighted Reciprocal Rank Fusion: score = sum(weight / (RRF_K + rank))."""
    scores, by_id = {}, {}
    for docs, w in ((dense, config.HYBRID_DENSE_WEIGHT), (keyword, config.HYBRID_BM25_WEIGHT)):
        for rank, d in enumerate(docs, 1):
            cid = d.metadata["chunk_id"]
            by_id[cid] = d
            scores[cid] = scores.get(cid, 0.0) + w / (config.RRF_K + rank)
    best = sorted(scores, key=scores.get, reverse=True)[:config.TOP_K]
    trace_log("score_meaning", "weighted RRF score, higher = better")
    trace_log("fused", [chunk_summary(by_id[c], include_text=False, score=scores[c], rank=i)
                        for i, c in enumerate(best, 1)])
    return [by_id[c] for c in best]


@traced
def pinned_declarations(user_id: str, policy_number: str) -> List[Document]:
    """Declarations chunks that are always sent (limits, deductibles, endorsements list)."""
    docs = vs.get_policy_chunks(user_id, policy_number, {"chunk_type": "declarations"}) if config.PIN_DECLARATIONS else []
    trace_log("pinned", [chunk_summary(d, include_text=False) for d in docs])
    return docs


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------
@traced
def retrieve(question: str, user_id: str, policy_number: str) -> List[Document]:
    """Return pinned Declarations chunks plus the top-k relevant chunks."""
    trace_log("strategy", "hybrid_rrf" if config.HYBRID_ENABLED else "dense_mmr")
    vector = vs.embed_question(question)
    pool = dense_candidates(vector, user_id, policy_number)

    if config.HYBRID_ENABLED:
        keyword = bm25_rank(question, user_id, policy_number, config.FETCH_K)
        found = rrf_fuse([d for d, _ in pool], keyword)
    else:
        found = mmr_search(vector, user_id, policy_number, pool)

    seen, result = set(), []
    for d in pinned_declarations(user_id, policy_number) + found:
        cid = d.metadata["chunk_id"]
        if cid not in seen:
            seen.add(cid)
            result.append(d)
    trace_log("final_order", [{"source_tag": f"S{i}", **chunk_summary(d, include_text=False)}
                              for i, d in enumerate(result, 1)])
    return result
