"""Unit tests for semantic chunking (pure, no DB/network)."""

import re

from src.services.chunker import (
    MAX_CHUNK_TOKENS,
    MIN_CHUNK_TOKENS,
    chunk_sections,
    count_tokens,
)
from src.services.document_parser import ParsedSection


def _section(content: str, heading: str = "Introduccion") -> ParsedSection:
    return ParsedSection(
        heading=heading,
        level=1,
        content=content,
        page_start=1,
        page_end=1,
        position=0,
    )


def test_short_section_single_chunk_with_prefix() -> None:
    section = _section("Una frase corta. Otra frase mas.")
    chunks = chunk_sections([section], "Manual")

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.content.startswith("[Documento: Manual] [Seccion: Introduccion]")
    assert chunk.chunk_index == 0
    assert chunk.metadata["section_type"] == "complete"
    assert chunk.metadata["heading"] == "Introduccion"
    assert chunk.metadata["page_start"] == 1
    assert chunk.metadata["heading_level"] == 1
    assert chunk.metadata["position"] == 0


def _oversized_content(n_sentences: int = 140) -> str:
    return " ".join(
        f"Esta es la frase numero {i} y contiene contenido de relleno "
        f"suficiente para acumular tokens de manera estable."
        for i in range(n_sentences)
    )


def test_oversized_section_splits_with_overlap_and_metadata() -> None:
    content = _oversized_content()
    assert count_tokens(content) > MAX_CHUNK_TOKENS

    chunks = chunk_sections([_section(content)], "Manual")

    # Multiple sub-chunks produced.
    assert len(chunks) > 1

    # Every chunk carries the contextual prefix and complete metadata.
    for i, chunk in enumerate(chunks):
        assert chunk.content.startswith("[Documento: Manual] [Seccion: Introduccion]")
        assert chunk.chunk_index == i
        assert chunk.metadata["section_type"] == "split"
        assert chunk.metadata["position"] == 0
        # Each chunk stays within (approximately) the token budget.
        assert count_tokens(chunk.content) <= MAX_CHUNK_TOKENS + 40
        # Tiny trailing remainder is merged, so no chunk is below the minimum.
        assert count_tokens(chunk.content) >= MIN_CHUNK_TOKENS

    # Overlap: adjacent chunks share at least one boundary sentence number.
    def sentence_ids(text: str) -> set[int]:
        return {int(m) for m in re.findall(r"frase numero (\d+)", text)}

    for first, second in zip(chunks, chunks[1:]):
        assert sentence_ids(first.content) & sentence_ids(second.content)


def test_empty_section_is_skipped() -> None:
    assert chunk_sections([_section("   ")], "Manual") == []
