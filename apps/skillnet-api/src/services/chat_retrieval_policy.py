"""Decide when the employee's general chat needs course documentation.

The lesson tutor and the general assistant share an endpoint, but not a retrieval
contract. A turn opened from a lesson must retrieve. A turn in ``/empleado/chat`` should
only pay for and expose course RAG when the learner asks about training material or
internal rules.

The router is deterministic: another LLM call would add latency, cost and a failure mode
before the actual answer, while provider tool-calling APIs are not uniform.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from typing import Protocol


class _MessageLike(Protocol):
    role: str
    message_metadata: dict | None


_CONTEXT_KEYS = frozenset({"node_id", "course_id", "document_ids", "nodeTitle"})

# These expressions mean "use my organization's learning material", rather than merely
# mentioning a topic that might also occur in a course. Accent folding happens first.
_COURSE_SCOPE_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"\b(?:mi|mis|el|los|este|estos|nuestro|nuestros)\s+(?:curso|cursos|leccion|lecciones|modulo|modulos|formacion)\b",
        r"\b(?:curso|cursos|leccion|lecciones|modulo|modulos)\s+(?:asignado|asignados|de\s+skillnet)\b",
        r"\b(?:documentacion|documento|documentos|manual|manuales|material|materiales)\b",
        r"\b(?:politica|politicas|protocolo|protocolos|normativa|procedimiento|procedimientos|regla|reglas)\s+(?:interna|internas|interno|internos|de\s+(?:la|mi|nuestra)\s+empresa)\b",
        r"\b(?:segun|dice|indica|aparece|pone|consta)\b.{0,48}\b(?:curso|leccion|manual|documento|material|skillnet)\b",
        r"\b(?:en|de)\s+skillnet\b",
        r"\b(?:mi|nuestra|la)\s+empresa\b.{0,48}\b(?:exige|dice|indica|permite|prohibe|obliga|recomienda)\b",
        r"\b(?:que|cual|cuales)\s+(?:curso|cursos)\b",
    )
)

_FOLLOW_UP_RE = re.compile(
    r"^(?:y\s+)?(?:que\s+mas|por\s+que|como|cuando|donde|cual|cuales|explicalo|"
    r"amplia|continua|sigue|resume|ponme\s+un\s+ejemplo)\b"
)


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def has_lesson_context(context: dict | None) -> bool:
    """Whether this turn was opened from a course/lesson surface."""
    if not context:
        return False
    return any(context.get(key) for key in _CONTEXT_KEYS)


def course_retrieval_required(
    question: str,
    context: dict | None,
    history: Sequence[_MessageLike] = (),
) -> bool:
    """Return whether this employee turn should run the course RAG ladder.

    A compact follow-up such as ``"¿y qué más?"`` inherits retrieval only from the
    immediately preceding grounded assistant response. This preserves conversational
    continuity without making the whole session permanently document-scoped.
    """
    if has_lesson_context(context):
        return True

    folded = " ".join(_fold(question).split())
    if any(pattern.search(folded) for pattern in _COURSE_SCOPE_PATTERNS):
        return True

    if not _FOLLOW_UP_RE.search(folded):
        return False
    for message in reversed(history):
        if message.role != "assistant":
            continue
        metadata = message.message_metadata or {}
        return metadata.get("grounding") in {"chunks", "chunks_fts", "document"}
    return False


__all__ = ["course_retrieval_required", "has_lesson_context"]
