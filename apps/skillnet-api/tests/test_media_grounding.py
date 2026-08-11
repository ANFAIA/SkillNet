"""Unit tests for the media grounding-context builder (pure, no DB/network)."""

import uuid

from src.services.media.grounding import (
    GroundedBundle,
    GroundedPassage,
    bundle_from_chunks,
    bundle_from_documents,
)


def _chunk(
    *,
    content: str,
    document_id: uuid.UUID,
    title: str = "Manual Alergenos",
    heading: str = "Los catorce alergenos",
    page: int = 2,
    position: int = 0,
    similarity: float = 0.9,
) -> dict:
    return {
        "chunk_id": uuid.uuid4(),
        "document_id": document_id,
        "content": content,
        "document_title": title,
        "similarity": similarity,
        "metadata": {"heading": heading, "page_start": page, "position": position},
    }


def test_chunk_bundle_assigns_stable_sequential_citation_ids() -> None:
    doc = uuid.uuid4()
    rows = [
        _chunk(content="El gluten es un alergeno.", document_id=doc, position=0),
        _chunk(content="El apio tambien.", document_id=doc, position=1, heading="Apio"),
    ]

    bundle = bundle_from_chunks(rows, mode="chunks")

    assert bundle.mode == "chunks"
    assert bundle.citation_ids() == ["c1", "c2"]
    # Ordered by document then in-document position (reused from retrieval.order_chunks).
    assert bundle.passages[0].text == "El gluten es un alergeno."
    assert bundle.passages[1].text == "El apio tambien."


def test_chunk_bundle_dedupes_keeping_highest_score() -> None:
    doc = uuid.uuid4()
    shared = "El gluten es un alergeno de declaracion obligatoria."
    rows = [
        _chunk(content=shared, document_id=doc, similarity=0.4),
        _chunk(content=shared, document_id=doc, similarity=0.95),
    ]

    bundle = bundle_from_chunks(rows, mode="chunks")

    # Dedup (from retrieval.dedupe_chunks) collapses to one, and ids stay contiguous.
    assert len(bundle.passages) == 1
    assert bundle.citation_ids() == ["c1"]


def test_prompt_context_carries_citation_markers() -> None:
    doc = uuid.uuid4()
    bundle = bundle_from_chunks(
        [_chunk(content="El gluten es un alergeno.", document_id=doc)], mode="chunks"
    )

    context = bundle.as_prompt_context()

    assert "[Fuente c1: Manual Alergenos > Los catorce alergenos, pag. 2]" in context
    assert "El gluten es un alergeno." in context


def test_citations_payload_shape() -> None:
    doc = uuid.uuid4()
    bundle = bundle_from_chunks([_chunk(content="x", document_id=doc)], mode="chunks_fts")

    payload = bundle.citations_payload()

    assert payload == [
        {
            "citation_id": "c1",
            "document": "Manual Alergenos",
            "section": "Los catorce alergenos",
            "page": 2,
            "document_id": str(doc),
        }
    ]


def test_document_bundle_marks_whole_document_and_caps_count() -> None:
    documents = [
        {"id": uuid.uuid4(), "title": f"Doc {i}", "full_text": f"cuerpo {i}"}
        for i in range(6)
    ]

    bundle = bundle_from_documents(documents)

    # Capped at _MAX_DOCUMENT_PASSAGES (4), sequential ids, honest "documento completo".
    assert len(bundle.passages) == 4
    assert bundle.mode == "document"
    assert bundle.citation_ids() == ["c1", "c2", "c3", "c4"]
    assert all(p.section == "documento completo" for p in bundle.passages)
    assert all(p.page is None for p in bundle.passages)


def test_document_bundle_skips_empty_full_text() -> None:
    documents = [
        {"id": uuid.uuid4(), "title": "Vacio", "full_text": "   "},
        {"id": uuid.uuid4(), "title": "Lleno", "full_text": "contenido real"},
    ]

    bundle = bundle_from_documents(documents)

    assert len(bundle.passages) == 1
    assert bundle.passages[0].source_title == "Lleno"
    assert bundle.passages[0].citation_id == "c1"


def test_empty_bundle_reports_empty() -> None:
    bundle = GroundedBundle(mode="empty", passages=[])

    assert bundle.is_empty()
    assert bundle.as_prompt_context() == ""
    assert bundle.citations_payload() == []


def test_passage_marker_without_section_or_page() -> None:
    passage = GroundedPassage(citation_id="c1", text="t", source_title="Solo Titulo")

    assert passage.marker() == "[Fuente c1: Solo Titulo]"
