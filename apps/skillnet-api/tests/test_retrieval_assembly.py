"""Unit tests for retrieval context assembly (pure, no DB/network)."""

import uuid

from src.services.retrieval import assemble_context, dedupe_chunks, order_chunks


def _chunk(
    *,
    content: str,
    document_id: uuid.UUID,
    title: str = "Manual Devoluciones",
    heading: str = "Plazos",
    page: int = 3,
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


def test_dedupe_keeps_highest_similarity() -> None:
    doc = uuid.uuid4()
    shared = "El plazo de devolucion es de 30 dias naturales desde la compra."
    low = _chunk(content=shared, document_id=doc, similarity=0.4)
    high = _chunk(content=shared, document_id=doc, similarity=0.95)

    result = dedupe_chunks([low, high])

    assert len(result) == 1
    assert result[0]["similarity"] == 0.95


def test_order_by_document_then_position() -> None:
    doc = uuid.uuid4()
    second = _chunk(content="B", document_id=doc, position=5)
    first = _chunk(content="A", document_id=doc, position=1)

    ordered = order_chunks([second, first])

    assert [c["content"] for c in ordered] == ["A", "B"]


def test_assemble_context_citation_markers() -> None:
    doc = uuid.uuid4()
    chunks = [
        _chunk(content="Texto uno.", document_id=doc, heading="Plazos", page=3),
        _chunk(content="Texto dos.", document_id=doc, heading="Excepciones", page=4),
    ]

    block, citations = assemble_context(chunks)

    assert "[Fuente 1: Manual Devoluciones > Plazos, pag. 3]" in block
    assert "[Fuente 2: Manual Devoluciones > Excepciones, pag. 4]" in block
    assert "Texto uno." in block
    assert "\n\n---\n\n" in block

    assert citations == [
        {"document": "Manual Devoluciones", "section": "Plazos", "page": 3},
        {"document": "Manual Devoluciones", "section": "Excepciones", "page": 4},
    ]


def test_assemble_context_without_heading_or_page() -> None:
    doc = uuid.uuid4()
    chunk = {
        "document_id": doc,
        "content": "Solo texto.",
        "document_title": "Doc",
        "similarity": 0.8,
        "metadata": {"heading": "", "position": 0},
    }

    block, citations = assemble_context([chunk])

    assert "[Fuente 1: Doc]" in block
    assert citations[0] == {"document": "Doc", "section": "", "page": None}
