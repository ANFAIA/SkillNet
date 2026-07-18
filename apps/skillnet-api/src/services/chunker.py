"""Semantic-first chunking with fixed-size fallback.

Pure functions (no I/O) so they are directly unit-testable. One chunk per
section when it fits the token budget; oversized sections fall back to a
paragraph/sentence greedy merge with a 2-sentence overlap between sub-chunks.
Every chunk carries a contextual prefix (document title + section heading).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import tiktoken

if TYPE_CHECKING:
    from src.services.document_parser import ParsedSection

MAX_CHUNK_TOKENS = 512
MIN_CHUNK_TOKENS = 50
OVERLAP_SENTENCES = 2

_enc = tiktoken.get_encoding("cl100k_base")

# Split on sentence terminators followed by whitespace. Python's ``re`` forbids
# variable-width lookbehind, so common Spanish abbreviations are re-merged after
# the naive split instead of being guarded inline.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_ABBREVIATIONS = {
    "sr", "sra", "dr", "dra", "ud", "uds", "etc", "pag", "vol", "art", "nro", "num",
}


@dataclass
class Chunk:
    content: str
    chunk_index: int
    metadata: dict


def count_tokens(text: str) -> int:
    return len(_enc.encode(text))


def split_sentences(text: str) -> list[str]:
    """Split text into sentences, re-joining known abbreviation boundaries."""
    sentences: list[str] = []
    for fragment in _SENTENCE_BOUNDARY.split(text):
        fragment = fragment.strip()
        if not fragment:
            continue
        if sentences:
            last_word = sentences[-1].rsplit(" ", 1)[-1].rstrip(".").lower()
            if last_word in _ABBREVIATIONS:
                sentences[-1] = f"{sentences[-1]} {fragment}"
                continue
        sentences.append(fragment)
    return sentences


def _prefix(document_title: str, heading: str) -> str:
    return f"[Documento: {document_title}] [Seccion: {heading}]"


def _metadata(section: ParsedSection, section_type: str) -> dict:
    return {
        "page_start": section.page_start,
        "page_end": section.page_end,
        "heading": section.heading,
        "heading_level": section.level,
        "position": section.position,
        "section_type": section_type,
    }


def _assemble(prefix: str, overlap: str, parts: list[str]) -> str:
    body = " ".join(p for p in parts if p)
    if overlap:
        body = f"{overlap}\n\n{body}"
    return f"{prefix}\n\n{body}"


def _fits(prefix: str, overlap: str, parts: list[str]) -> bool:
    return count_tokens(_assemble(prefix, overlap, parts)) <= MAX_CHUNK_TOKENS


def _overlap_text(parts: list[str]) -> str:
    sentences = split_sentences(" ".join(parts))
    return " ".join(sentences[-OVERLAP_SENTENCES:]) if sentences else ""


def _units(cleaned: str, prefix: str) -> list[str]:
    """Break oversized content into packing units: paragraphs, splitting any
    paragraph that alone exceeds the budget into sentences."""
    units: list[str] = []
    for para in cleaned.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if _fits(prefix, "", [para]):
            units.append(para)
        else:
            units.extend(split_sentences(para) or [para])
    return units


def chunk_sections(
    sections: list[ParsedSection], document_title: str
) -> list[Chunk]:
    chunks: list[Chunk] = []
    index = 0

    for section in sections:
        cleaned = section.content.strip()
        if not cleaned:
            continue
        prefix = _prefix(document_title, section.heading)

        if count_tokens(cleaned) <= MAX_CHUNK_TOKENS:
            chunks.append(
                Chunk(
                    content=f"{prefix}\n\n{cleaned}",
                    chunk_index=index,
                    metadata=_metadata(section, "complete"),
                )
            )
            index += 1
            continue

        # Oversized section: greedy-merge units within the token budget.
        current: list[str] = []
        overlap = ""
        for unit in _units(cleaned, prefix):
            candidate = current + [unit]
            if current and not _fits(prefix, overlap, candidate):
                chunks.append(
                    Chunk(
                        content=_assemble(prefix, overlap, current),
                        chunk_index=index,
                        metadata=_metadata(section, "split"),
                    )
                )
                index += 1
                overlap = _overlap_text(current)
                current = [unit]
            else:
                current = candidate

        if current:
            body = " ".join(current)
            if count_tokens(body) < MIN_CHUNK_TOKENS and chunks:
                # Merge a tiny trailing remainder into the previous chunk.
                chunks[-1].content += "\n\n" + body
            else:
                chunks.append(
                    Chunk(
                        content=_assemble(prefix, overlap, current),
                        chunk_index=index,
                        metadata=_metadata(section, "split"),
                    )
                )
                index += 1

    return chunks
