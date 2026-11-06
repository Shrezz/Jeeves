"""
chunker.py
==========
Turns parsed layout Elements into LangChain Documents ready for Chroma
(Decision D3: structure-aware chunking).

Rules
-----
1. A new H1/H2/H3 heading closes the current chunk and starts a new one.
2. Every chunk's text starts with its heading path, e.g.
   "Section I - Exclusions > Water", so the embedding knows the context.
3. Each table is its own chunk. A table that continues on the next page
   (same header row, no heading in between) is merged. Only a very long
   table (over 1.5 x CHUNK_SIZE_CHARS) is split, by whole rows, with its
   title repeated on each piece.
4. Long prose sections are split at numbered-item / sentence boundaries
   with a small overlap (config.CHUNK_SIZE_CHARS / CHUNK_OVERLAP_CHARS).
5. Each chunk carries metadata (Decision D2) used for filtering and citations.

chunk_type values: cover, declarations, definitions, coverage, perils,
exclusion, conditions, liability, endorsement, california, general
"""
import re
from typing import Dict, List, Optional

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from . import config
from .pdf_parser import Element
from .tracing import chunk_summary, trace_log, traced

ENDORSEMENT_CODE = re.compile(r"\b(MC \d{2} \d{2}|MC CA \d{2})\b")

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=config.CHUNK_SIZE_CHARS,
    chunk_overlap=config.CHUNK_OVERLAP_CHARS,
    separators=["\n", ". ", "; ", ", ", " "],   # paragraphs (numbered items) first, then sentences
)


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------
def _chunk_type(h1: str, is_cover: bool) -> str:
    """Derive a coarse chunk type from the H1 section title."""
    if is_cover:
        return "cover"
    t = h1.lower()
    rules = [("declarations", "declarations"), ("definitions", "definitions"), ("endorsement", "endorsement"),
             ("exclusion", "exclusion"), ("perils", "perils"), ("california", "california"),
             ("section ii", "liability"), ("conditions", "conditions"), ("coverages", "coverage"),
             ("how to read", "general")]
    for key, value in rules:
        if key in t:
            return value
    return "general"


def _table_to_text(rows: List[List[str]]) -> str:
    """Render a table as 'Header: value; Header: value' lines (embeds better than grids)."""
    header, lines = rows[0], []
    for row in rows[1:]:
        pairs = [f"{h}: {v}" for h, v in zip(header, row) if v and h.lower() not in ("s.no", "#")]
        lines.append("; ".join(pairs))
    return "\n".join(lines)


def _split_large_table(doc: Document) -> List[Document]:
    """Split a very long table into row groups. Rows are never cut and every
    piece repeats the table title, so each piece still makes sense alone."""
    limit = int(config.CHUNK_SIZE_CHARS * 1.5)
    if len(doc.page_content) <= limit:
        return [doc]
    title, *rows = doc.page_content.split("\n")
    pieces, current = [], []
    for row in rows:
        if current and len("\n".join(current + [row])) > limit:
            pieces.append(current)
            current = []
        current.append(row)
    pieces.append(current)
    return [Document(page_content=f"{title}\n" + "\n".join(p), metadata=dict(doc.metadata)) for p in pieces]


# ---------------------------------------------------------------------------
# Chunk builder
# ---------------------------------------------------------------------------
class _ChunkBuilder:
    """Accumulates elements into chunks while tracking the heading path."""

    def __init__(self, base_meta: Dict):
        self.base_meta = base_meta
        self.h = {"h1": "", "h2": "", "h3": ""}
        self.buffer: List[str] = []
        self.buffer_page: Optional[int] = None
        self.docs: List[Document] = []
        self.last_table: Optional[Document] = None     # for merging tables across pages

    # -- context ------------------------------------------------------------
    def heading_path(self) -> str:
        return " > ".join(v for v in (self.h["h1"], self.h["h2"], self.h["h3"]) if v)

    def _meta(self, page: int, is_table: bool, is_cover: bool = False) -> Dict:
        path = self.heading_path() or ("Cover Page" if is_cover else "Document")
        code = ENDORSEMENT_CODE.search(self.h["h2"]) if "endorsement" in self.h["h1"].lower() else None
        return {**self.base_meta,
                "heading_path": path,
                "section": self.h["h1"] or path,
                "page": page,
                "chunk_type": _chunk_type(self.h["h1"], is_cover),
                "is_table": is_table,
                "endorsement_code": code.group(1) if code else ""}   # Chroma rejects None

    # -- emitters -----------------------------------------------------------
    def flush_text(self) -> None:
        """Close the current prose chunk, splitting it if it is too long."""
        if not self.buffer:
            return
        body = "\n".join(self.buffer)
        meta = self._meta(self.buffer_page, is_table=False, is_cover=self.buffer_page == 1)
        for piece in _splitter.split_text(body):
            self.docs.append(Document(page_content=f"{meta['heading_path']}\n{piece}", metadata=dict(meta)))
        self.buffer, self.buffer_page = [], None

    def add_heading(self, el: Element) -> None:
        self.flush_text()
        self.last_table = None
        if el.kind == "h1":
            self.h = {"h1": el.text, "h2": "", "h3": ""}
        elif el.kind == "h2":
            self.h["h2"], self.h["h3"] = el.text, ""
        else:
            self.h["h3"] = el.text

    def add_text(self, el: Element) -> None:
        if self.buffer_page is None:
            self.buffer_page = el.page
        self.buffer.append(el.text)
        self.last_table = None

    def add_table(self, el: Element) -> None:
        self.flush_text()
        rows = el.rows
        # Continuation of the previous table on a new page: same header, no heading in between.
        if self.last_table is not None and self.last_table.metadata.get("_header") == rows[0]:
            self.last_table.page_content += "\n" + _table_to_text(rows)
            return
        meta = self._meta(el.page, is_table=True)
        doc = Document(page_content=f"{meta['heading_path']} (table)\n{_table_to_text(rows)}", metadata=meta)
        doc.metadata["_header"] = rows[0]               # temporary, removed in finalize()
        self.docs.append(doc)
        self.last_table = doc

    def finalize(self) -> List[Document]:
        self.flush_text()
        out: List[Document] = []
        for d in self.docs:
            d.metadata.pop("_header", None)
            out.extend(_split_large_table(d) if d.metadata["is_table"] else [d])
        return out


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------
@traced
def build_chunks(elements: List[Element], base_meta: Dict) -> List[Document]:
    """Create chunk Documents. base_meta holds user_id, policy_number, form, etc."""
    builder = _ChunkBuilder(base_meta)
    for el in elements:
        if el.kind in ("h1", "h2", "h3"):
            builder.add_heading(el)
        elif el.kind == "table":
            builder.add_table(el)
        else:                                           # "text" and "cover"
            builder.add_text(el)
    docs = builder.finalize()

    # Fixed, deterministic chunk ids so re-ingesting replaces rather than duplicates (Decision D9).
    for i, d in enumerate(docs):
        d.metadata["chunk_id"] = f"{base_meta['user_id']}::{base_meta['policy_number']}::{base_meta['doc_version']}::{i:04d}"
        d.metadata["chunk_index"] = i
    trace_log("chunk_count", len(docs))
    trace_log("chunks", [chunk_summary(d, include_text=False, index=d.metadata["chunk_index"]) for d in docs])
    return docs
