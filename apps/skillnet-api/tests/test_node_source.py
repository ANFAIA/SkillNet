"""Per-node source briefs: schema seed, prompt, and persisted Markdown."""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

from src.knowledge_pack.node_source import draft_is_usable, seed_node_source
from src.llm.prompts.source import NODE_SOURCE_WRITER_SYSTEM, build_node_source_prompt
from src.models import DocumentOrigin, DocumentStatus
from src.services.document_service import DocumentService


def test_seed_node_source_is_the_schema_point_not_the_whole_course() -> None:
    course = SimpleNamespace(
        title="Devoluciones en tienda",
        description="Politica comercial de la pyme",
        outcome=None,
    )
    node = SimpleNamespace(
        title="Plazo de devolucion",
        summary="El cliente tiene 14 dias naturales desde la entrega.",
        outcome="Calcular el ultimo dia habil para aceptar una devolucion.",
    )

    text = seed_node_source(course=course, node=node)

    assert text.startswith("# Plazo de devolucion")
    assert "14 dias naturales" in text
    assert "Calcular el ultimo dia habil" in text
    assert "Devoluciones en tienda" in text


def test_node_source_prompt_asks_for_this_point_only() -> None:
    prompt = build_node_source_prompt(
        course_title="Devoluciones",
        course_idea="Tienda de barrio",
        node_title="Plazo de devolucion",
        summary="El cliente tiene 14 dias naturales desde la entrega.",
        outcome="Decir el ultimo dia en que se acepta la caja.",
    )

    assert prompt.rstrip().endswith("Escribe el documento fuente de este punto.")
    assert "Plazo de devolucion" in prompt
    assert "14 dias naturales" in prompt
    assert "##" in NODE_SOURCE_WRITER_SYSTEM
    assert "UN punto" in NODE_SOURCE_WRITER_SYSTEM


def test_a_thin_model_draft_is_rejected_in_favour_of_the_schema_seed() -> None:
    assert draft_is_usable("ok") is False
    assert draft_is_usable("Hecho util. " * 20) is True


async def test_persist_generated_markdown_keeps_full_text_readable(tmp_path: Path, monkeypatch):
    from src.config import settings

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))

    class FakeRepo:
        def __init__(self) -> None:
            self.rows = []

        async def create(self, **kwargs):
            row = SimpleNamespace(id=uuid.uuid4(), **kwargs)
            self.rows.append(row)
            return row

        async def update(self, doc, **kwargs):
            for key, value in kwargs.items():
                setattr(doc, key, value)
            return doc

    service = DocumentService(FakeRepo())
    text = "## Plazo\nEl cliente tiene 14 dias naturales desde la entrega.\n"
    doc = await service.persist_generated_markdown(
        org_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
        title="Plazo de devolucion",
        text=text,
        status=DocumentStatus.READY,
        full_text=text,
        page_count=1,
    )

    assert doc.origin is DocumentOrigin.GENERATED
    assert doc.status is DocumentStatus.READY
    assert doc.full_text == text
    assert Path(doc.storage_path).read_text(encoding="utf-8") == text.strip()
