"""Pure source-shaping helpers shared by the v1 content graph and the v2 schema graph.

Extracted verbatim from ``src/agents/content/nodes.py`` — a code move with **no**
behaviour change, covered by ``tests/test_generation_pipeline.py``.

Why the move exists (§4 of ``docs/design/v2-dynamic-courses.md``): the v2 schema
graph needs the same source shaping, but the v1 nodes are *not* reusable because
they write v1 job states (``extracting``/``structuring``) and publish generic
``step`` events. So only the pure parts are shared; the graph nodes themselves are
new. Nothing in this module touches the database, the network, or the SSE bus.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

# A document shorter than this many pages is fed to the LLM whole; anything
# bigger goes through chunk retrieval.
FULL_TEXT_PAGE_THRESHOLD = 5
CHARS_PER_PAGE = 2000


class _PageCountable(Protocol):
    """Just enough of ``Document`` to estimate its length."""

    page_count: int | None
    full_text: str | None


class _HasContent(Protocol):
    """Just enough of ``DocumentChunk`` to assemble its text."""

    content: str


def estimate_pages(doc: _PageCountable) -> int:
    if doc.page_count:
        return doc.page_count
    return max(1, len(doc.full_text or "") // CHARS_PER_PAGE)


# Pattern that matches the "[Documento: ...] [Seccion: ...]" prefix added by the
# chunker.  These prefixes are useful for RAG chat (source attribution) but must
# be stripped from the generation pipeline so the LLM does not bake citation
# artifacts into the course content shown to end users.
_CHUNK_PREFIX_RE = re.compile(
    r"^\[Documento:\s*[^\]]*\]\s*\[Seccion:\s*[^\]]*\]\s*", re.MULTILINE
)


def strip_chunk_prefix(text: str) -> str:
    return _CHUNK_PREFIX_RE.sub("", text).lstrip()


def assemble_chunk_text(chunks: list[_HasContent]) -> str:
    return "\n\n".join(strip_chunk_prefix(chunk.content) for chunk in chunks)


def themes_list(parsed: Any) -> list[dict]:
    if isinstance(parsed, dict):
        return parsed.get("themes") or []
    if isinstance(parsed, list):
        return parsed
    return []
