"""Per-node source briefs, written after the schema exists.

A course created from a title has no uploaded manual. The pack generator still
needs an excerpt. This module writes one short reference document per node from
the schema fields (and an optional model draft), then stores it as an ordinary
generated Markdown document so runtime retrieval stays on the existing path.
"""

from __future__ import annotations

from typing import Any

from src.core.language import DEFAULT_LANGUAGE, Language
from src.models import Course, CourseNode, DocumentStatus
from src.repositories.document_repo import DocumentRepository
from src.services.language_policy import language_for_course
from src.services.document_service import DocumentService

_MIN_DRAFT_CHARS = 120

#: The four fixed strings this module writes. A table, not an i18n framework: this is
#: the whole inventory of learner-visible prose the backend produces without a model,
#: and two columns of four rows need no catalogues, extraction step or workflow to stay
#: correct. If a third language ever arrives, this table is where it is missed.
_LABELS: dict[Language, dict[str, str]] = {
    "es": {
        "node": "Punto",
        "outcome": "Resultado",
        "covers": "Que cubre",
        "course": "Curso",
    },
    "en": {
        "node": "Point",
        "outcome": "Outcome",
        "covers": "What it covers",
        "course": "Course",
    },
}


def seed_node_source(
    *, course: Course, node: CourseNode, language: Language | None = None
) -> str:
    """Deterministic briefing from the schema when no document and no model draft.

    Worth translating even though it is a fallback: it is what the pack generator reads
    whenever the drafting call fails or comes back thin, so on a bad provider day these
    headings are the only source an English course has.
    """

    labels = _LABELS[language_for_course(course, explicit=language) or DEFAULT_LANGUAGE]
    title = (getattr(node, "title", None) or "").strip() or labels["node"]
    summary = (getattr(node, "summary", None) or "").strip()
    outcome = (getattr(node, "outcome", None) or "").strip()
    course_title = (getattr(course, "title", None) or "").strip()
    course_idea = (
        getattr(course, "description", None) or getattr(course, "outcome", None) or ""
    ).strip()

    parts = [f"# {title}", ""]
    if outcome:
        parts.extend([f"## {labels['outcome']}", outcome, ""])
    if summary:
        parts.extend([f"## {labels['covers']}", summary, ""])
    if course_title or course_idea:
        parts.append(f"## {labels['course']}")
        if course_title:
            parts.append(course_title)
        if course_idea:
            parts.append(course_idea)
    return "\n".join(parts).strip() + "\n"


def draft_is_usable(text: str) -> bool:
    return len(text.strip()) >= _MIN_DRAFT_CHARS


async def persist_generated_node_source(
    db: Any, node: CourseNode, text: str, course: Course
) -> None:
    """Attach a generated Markdown document to the node and keep ``full_text`` readable."""

    service = DocumentService(DocumentRepository(db))
    document = await service.persist_generated_markdown(
        org_id=node.org_id,
        created_by=getattr(course, "created_by", None),
        title=node.title,
        text=text,
        status=DocumentStatus.READY,
        full_text=text,
        page_count=1,
    )
    node.source_document_id = document.id


__all__ = [
    "draft_is_usable",
    "persist_generated_node_source",
    "seed_node_source",
]
