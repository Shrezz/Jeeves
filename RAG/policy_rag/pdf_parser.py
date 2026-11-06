"""
pdf_parser.py
=============
Structure-aware PDF reading (Decision D3).

Turns a policy PDF into an ordered list of layout Elements:
    heading (level 1/2/3), paragraph text, table, or cover text.

Why not plain text extraction? The policies are organised by headings and
tables. Knowing where a heading or table starts lets the chunker keep a whole
table together and label every chunk with its heading path, which is what
makes retrieval accurate for "is X covered and how much" questions.

Steps per page:
    1. Detect tables with PyMuPDF and read each cell by clipping its box
       (direct table extraction scrambles "$620,000" into "$620 000 ,").
    2. Read the remaining text blocks, skipping running header/footer bands
       and anything inside a table box.
    3. Classify each text block as a heading by font size (config H*_MIN_SIZE).
    4. Sort everything top-to-bottom so the document order is preserved.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import pymupdf

from . import config
from .tracing import trace_log, traced

NUMBERED_ITEM = re.compile(r"^\d+\.\s")
PARAGRAPH_GAP_PT = 3.0      # vertical gap larger than this starts a new paragraph


@dataclass
class Element:
    """One piece of the document in reading order."""
    kind: str                       # "h1" | "h2" | "h3" | "text" | "table" | "cover"
    page: int                       # 1-based page number
    y: float                        # top coordinate, used for ordering
    text: str = ""                  # heading or paragraph text
    rows: List[List[str]] = field(default_factory=list)   # table rows (first row = header)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _clean(text: str) -> str:
    """Collapse whitespace and drop zero-width characters."""
    return " ".join(text.replace("​", "").split())


def _in_any(rect: pymupdf.Rect, boxes: List[pymupdf.Rect]) -> bool:
    """True if the centre of rect lies inside one of the boxes."""
    cx, cy = (rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2
    return any(b.x0 <= cx <= b.x1 and b.y0 <= cy <= b.y1 for b in boxes)


def _heading_level(size: float, bold: bool) -> Optional[str]:
    """Map a font size to a heading level using the template's sizes."""
    if size >= config.H1_MIN_SIZE:
        return "h1"
    if size >= config.H2_MIN_SIZE:
        return "h2"
    if size >= config.H3_MIN_SIZE and bold:
        return "h3"
    return None


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------
def _extract_tables(page: pymupdf.Page, page_no: int):
    """Return (elements, bounding boxes) for multi-column tables on the page."""
    elements, boxes = [], []
    for tab in page.find_tables().tables:
        if not tab.rows or len(tab.rows[0].cells) < 2:
            continue                                   # 1-column boxes are callouts, keep as text
        rows = []
        for row in tab.rows:
            cells = [_clean(page.get_text("text", clip=pymupdf.Rect(c))) if c else "" for c in row.cells]
            if any(cells):
                rows.append(cells)
        if rows:
            box = pymupdf.Rect(tab.bbox)
            boxes.append(box)
            elements.append(Element(kind="table", page=page_no, y=box.y0, rows=rows))
    return elements, boxes


# ---------------------------------------------------------------------------
# Text blocks
# ---------------------------------------------------------------------------
def _extract_text(page: pymupdf.Page, page_no: int, table_boxes: List[pymupdf.Rect]) -> List[Element]:
    """Return heading and paragraph elements, excluding header/footer and tables.

    Works line by line (not block by block) because PyMuPDF can merge a
    heading and the paragraph next to it into one block.
    """
    top, bottom = config.HEADER_BAND_PT, page.rect.height - config.FOOTER_BAND_PT

    # 1. Collect usable lines with their style.
    lines = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:                     # 0 = text, 1 = image
            continue
        for ln in block["lines"]:
            rect = pymupdf.Rect(ln["bbox"])
            text = _clean("".join(s["text"] for s in ln["spans"]))
            if not text or rect.y1 <= top or rect.y0 >= bottom or _in_any(rect, table_boxes):
                continue
            span = max(ln["spans"], key=lambda s: len(s["text"]))      # dominant span
            kind = "cover" if page_no == 1 else (_heading_level(span["size"], "Bold" in span["font"]) or "text")
            lines.append((rect, kind, text))
    lines.sort(key=lambda t: (round(t[0].y0), t[0].x0))

    # 2. Group consecutive lines into elements.
    elements: List[Element] = []
    prev_rect, prev_kind = None, None
    for rect, kind, text in lines:
        gap = rect.y0 - prev_rect.y1 if prev_rect else 99
        same_para = (kind == prev_kind and gap < PARAGRAPH_GAP_PT and not NUMBERED_ITEM.match(text))
        if same_para and elements:
            elements[-1].text += " " + text
        else:
            elements.append(Element(kind=kind, page=page_no, y=rect.y0, text=text))
        prev_rect, prev_kind = rect, kind
    return elements


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------
@traced
def parse_pdf(path: Path) -> List[Element]:
    """Parse a policy PDF into ordered layout elements."""
    elements: List[Element] = []
    with pymupdf.open(path) as doc:
        pages = len(doc)
        for index, page in enumerate(doc):
            page_no = index + 1
            tables, boxes = _extract_tables(page, page_no)
            texts = _extract_text(page, page_no, boxes)
            # stable sort keeps the original order of elements that share a y value
            elements.extend(sorted(tables + texts, key=lambda e: e.y))
    counts = {}
    for e in elements:
        counts[e.kind] = counts.get(e.kind, 0) + 1
    trace_log("file", str(path))
    trace_log("pages", pages)
    trace_log("element_counts", counts)
    return elements


def full_text(elements: List[Element]) -> str:
    """Plain text of the whole document (used to read the policy number)."""
    parts = []
    for e in elements:
        parts.append(" | ".join(" | ".join(r) for r in e.rows) if e.kind == "table" else e.text)
    return "\n".join(parts)
