"""Page-aware policy chunking with section labels and token overlap."""

from __future__ import annotations

import re
from typing import Sequence
from uuid import NAMESPACE_URL, uuid5

import tiktoken

from .types import PolicyChunk, PolicyPage

_SECTION_HEADING = re.compile(
    r"^\s*((?:section\s+)?\d+(?:\.\d+)*(?:[.)])?\s+[^\n]{2,120})\s*$",
    re.IGNORECASE,
)


def _page_sections(text: str) -> list[tuple[str | None, str]]:
    sections: list[tuple[str | None, str]] = []
    current_label: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            if current_lines and current_lines[-1]:
                current_lines.append("")
            continue
        heading = _SECTION_HEADING.match(stripped)
        if heading:
            body = "\n".join(current_lines).strip()
            if body:
                sections.append((current_label, body))
            current_label = heading.group(1).strip()
            current_lines = []
        else:
            current_lines.append(stripped)

    body = "\n".join(current_lines).strip()
    if body:
        sections.append((current_label, body))
    return sections


def chunk_policy_pages(
    pages: Sequence[PolicyPage],
    *,
    user_id: str,
    policy_id: str,
    policy_version: str,
    max_tokens: int = 600,
    overlap_tokens: int = 60,
    encoding_name: str = "cl100k_base",
) -> list[PolicyChunk]:
    """Chunk each page/section independently and retain its citation metadata.

    The 600-token default is within the requirements' 400–700 token starting
    range. Tokenization should be aligned with the selected embedding model.
    """
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    if overlap_tokens < 0 or overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be in [0, max_tokens)")

    encoding = tiktoken.get_encoding(encoding_name)
    chunks: list[PolicyChunk] = []
    stride = max_tokens - overlap_tokens

    for page in pages:
        for section, text in _page_sections(page.text):
            tokens = encoding.encode(text)
            for start in range(0, len(tokens), stride):
                content = encoding.decode(tokens[start : start + max_tokens]).strip()
                if content:
                    stable_key = (
                        f"{policy_id}:{policy_version}:{page.page}:{section or ''}:"
                        f"{start}:{content}"
                    )
                    chunks.append(
                        PolicyChunk(
                            id=str(uuid5(NAMESPACE_URL, stable_key)),
                            user_id=user_id,
                            policy_id=policy_id,
                            policy_version=policy_version,
                            page=page.page,
                            section=section,
                            content=content,
                            embedding=(),
                        )
                    )
                if start + max_tokens >= len(tokens):
                    break
    return chunks
