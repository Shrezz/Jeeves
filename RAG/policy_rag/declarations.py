"""Read explicitly labelled rows from a text PDF's declarations (no model or index)."""

import json
import re
import sys
from typing import TypedDict

import pymupdf


class Declaration(TypedDict):
    kind: str
    label: str
    value: str
    page: int


_LABELS = {
    "number": ("policy number", "policy number / version"),
    "name": ("policy label", "policy name"),
    "issuer": ("fictional issuer", "issuer", "insurance company", "insurer"),
    "holder": ("named policyholder", "named insured", "policyholder"),
    "location": ("covered location", "insured location", "property address", "dwelling"),
    "term": ("policy period", "policy term"),
    "deductible": ("applicable deductible", "flat deductible", "deductible",
                   "wind/hail deductible", "all other perils deductible"),
    "limit": ("eligible-expense limit", "coverage limit"),
    "endorsement": ("attached endorsement", "endorsements"),
}
_KIND = {label: kind for kind, labels in _LABELS.items() for label in labels}
_HEADING = re.compile(r"^(?:\d+\s*[./:\-]?\s*)?(?:policy\s+)?declarations(?:\s+page)?$", re.I)
_SECTION = re.compile(r"^\d+(?:\.\d+)*[.)]?\s+[A-Za-z]")


def extract_declarations(pdf: bytes) -> list[Declaration]:
    """Support table rows and vertically stacked labels on early declarations pages."""
    fields: list[Declaration] = []
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        if document.needs_pass:
            return []
        for page_index in range(min(len(document), 8)):
            blocks = document[page_index].get_text("blocks", sort=True)
            in_declarations = False
            started_rows = False
            consumed = -1
            for i, block in enumerate(blocks):
                lines = block[4].strip().splitlines()
                if i == consumed or not lines or block[6] != 0:
                    continue
                first = " ".join(lines[0].split())
                if _HEADING.fullmatch(first):
                    in_declarations = True
                    started_rows = False
                    continue
                if not in_declarations:
                    continue
                if _SECTION.match(first):
                    in_declarations = False
                    continue
                label, _, inline = first.partition(":")
                kind = _KIND.get(label.casefold())
                if not kind:
                    if started_rows:
                        in_declarations = False
                    continue
                value = " ".join(filter(None, [inline.strip(), *(s.strip() for s in lines[1:])]))
                if not value and i + 1 < len(blocks):
                    # A stacked label can occupy its own text block. Do not borrow
                    # text from a remote column, a later paragraph, or another row.
                    following = blocks[i + 1]
                    pieces = following[4].strip().splitlines()
                    if (following[6] == 0 and pieces and abs(following[0] - block[0]) <= 4
                            and 0 <= following[1] - block[3] <= 16
                            and pieces[0].partition(":")[0].strip().casefold() not in _KIND
                            and not _SECTION.match(pieces[0])):
                        value = " ".join(s.strip() for s in pieces)
                        consumed = i + 1
                if value and len(value) <= 500:
                    started_rows = True
                    fields.append({"kind": kind, "label": label, "value": value, "page": page_index + 1})
    return fields


if __name__ == "__main__":
    print(json.dumps({"fields": extract_declarations(sys.stdin.buffer.read())}))
