"""Pure source- and response-shaping helpers for the content and schema graphs.

The source-shaping half (``estimate_pages`` .. ``assemble_chunk_text``) was extracted
verbatim from ``src/agents/content/nodes.py`` — a code move with **no** behaviour
change, covered by ``tests/test_generation_pipeline.py``.

Why the move exists (§4 of ``docs/design/v2-dynamic-courses.md``): the v2 schema
graph needs the same source shaping, but the v1 nodes are *not* reusable because
they write v1 job states (``extracting``/``structuring``) and publish generic
``step`` events. So only the pure parts are shared; the graph nodes themselves are
new. Nothing in this module touches the database, the network, or the SSE bus.

The response-shaping half (``themes_list`` and everything after it) answers one
question for every LLM step of the pipeline: the prompt asked for an object, the model
sent something else — what did it mean? See its section comment below.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from src.core.exceptions import LLMError

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


# --------------------------------------------------------------------------- #
# Response shaping: the prompt asked for an object, the model sent a list
# --------------------------------------------------------------------------- #
# Every structured step of the pipeline asks for a JSON *object* wrapping one or two
# arrays (``{"themes": [...]}``, ``{"modules": [...]}``, ``{"lessons": [...],
# "exercises": [...]}``, ``{"passed": ..., "issues": [...]}``). Models drop the wrapper
# and send the bare array often enough that it is a shape to expect, not a bug to
# report — and the enforced JSON modes do not help: ollama's ``format: "json"`` and
# OpenAI's ``response_format: json_object`` both guarantee *syntax*, never the schema.
#
# ``themes_list`` has tolerated it since v1 and ``src/agents/schema/nodes.py`` copied it
# for nodes. The two sites that did not were the two that broke: a bare list reaching
# ``generate_modules`` raised ``'list' object has no attribute 'get'``, and one reaching
# ``design_structure`` was quietly swapped for an empty course.
#
# Each helper below coerces to the documented shape when the array can be identified —
# and it always can, because the wrapper has exactly one array-valued field per step —
# or raises with what it actually received. What must not happen is a bare
# ``isinstance`` guard that discards a full, usable answer for having no wrapper.


def _dict_items(value: Any) -> list[dict]:
    """The dict elements of ``value``, or ``[]`` when it is not a list of them."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def themes_list(parsed: Any) -> list[dict]:
    """The extracted themes, from ``{"themes": [...]}`` or a bare list.

    Non-dict elements are dropped rather than passed through: ``_auto_create_skills``
    and ``build_structure_prompt`` both index into each theme, so a model answering
    ``["higiene", "alergenos"]`` used to travel four nodes and die in ``publish`` with
    ``'str' object has no attribute 'get'`` — the same bug as the module one, just
    further from its cause.
    """
    if isinstance(parsed, dict):
        return _dict_items(parsed.get("themes"))
    return _dict_items(parsed)


def describe_payload(parsed: Any) -> str:
    """What arrived, in a form an admin can act on: type, size and a short sample."""
    kind = type(parsed).__name__
    if isinstance(parsed, dict):
        keys = ", ".join(repr(key) for key in list(parsed)[:6]) or "no keys"
        return f"{kind} with {len(parsed)} key(s) ({keys})"
    if isinstance(parsed, list):
        types = sorted({type(item).__name__ for item in parsed[:8]})
        sample = repr(parsed[0])[:120] if parsed else "empty"
        return f"{kind} of {len(parsed)} item(s) of type {'/'.join(types) or 'none'}: {sample}"
    return f"{kind}: {repr(parsed)[:120]}"


def outline_dict(parsed: Any) -> dict:
    """The course outline as a dict, accepting a bare list of module specs.

    ``STRUCTURE_DESIGNER_SYSTEM`` asks for
    ``{"title", "description", "outcome", "modules": [...]}``, so a bare list can only
    be ``modules``. The title is deliberately *not* invented here: ``publish`` already
    defaults it to ``"Curso"``, and a second default would hide the omission.
    """
    if isinstance(parsed, dict):
        outline = dict(parsed)
        outline["modules"] = _dict_items(outline.get("modules"))
        return outline

    modules = _dict_items(parsed)
    if not modules:
        raise LLMError(
            "The structure designer did not return a course outline. Expected an object "
            'like {"title": ..., "modules": [...]} or a bare list of module objects; '
            f"received {describe_payload(parsed)}."
        )
    return {"modules": modules}


def _looks_like_exercise(item: dict) -> bool:
    """``{"type": str, "content": {...}, "position": int}`` — the exercise shape.

    The discriminator is ``content``, not ``type``: both shapes may carry a ``type``
    key, but a lesson's ``content`` is Markdown *text* and an exercise's is the jsonb
    object from ``docs/design/data-model.md``.
    """
    if isinstance(item.get("content"), dict):
        return True
    return "type" in item and "content" not in item and "title" not in item


def _looks_like_lesson(item: dict) -> bool:
    """``{"title": str, "position": int, "content": "<markdown>"}`` — the lesson shape."""
    return isinstance(item.get("content"), str) or "title" in item


def module_payload(parsed: Any) -> dict:
    """``{"lessons": [...], "exercises": [...]}`` out of whatever the generator sent.

    Accepts the documented object, a bare list, or a single bare item. A bare list is
    split by element shape rather than assumed to be one of the two arrays: models that
    drop the wrapper also flatten both arrays into one list, and a lesson is told from
    an exercise by whether its ``content`` is Markdown or jsonb.

    Raises :class:`LLMError` when nothing in the payload is a lesson or an exercise —
    there is no honest way to build a module out of it, and inventing an empty one would
    publish a course with blank modules.
    """
    if isinstance(parsed, dict) and ("lessons" in parsed or "exercises" in parsed):
        return {
            "lessons": _dict_items(parsed.get("lessons")),
            "exercises": _dict_items(parsed.get("exercises")),
        }

    items = [parsed] if isinstance(parsed, dict) else parsed
    lessons: list[dict] = []
    exercises: list[dict] = []
    for item in _dict_items(items) if isinstance(items, list) else []:
        if _looks_like_exercise(item):
            exercises.append(item)
        elif _looks_like_lesson(item):
            lessons.append(item)

    if not lessons and not exercises:
        raise LLMError(
            "The module generator did not return lessons or exercises. Expected an "
            'object like {"lessons": [...], "exercises": [...]}; received '
            f"{describe_payload(parsed)}."
        )
    return {"lessons": lessons, "exercises": exercises}


def review_report(parsed: Any) -> dict:
    """The quality report as a dict, accepting a bare list of issues.

    Never raises. The reviewer is a gate, not a producer: by the time it runs the whole
    course exists, and a report that cannot be read must degrade to "not reviewed" the
    same way a provider failure does (``tests/test_review_degrades.py``). A bare list is
    the ``issues`` array — the only array in the requested shape — and keeping it is
    what lets ``refine_content`` still act on the findings.
    """
    if isinstance(parsed, dict):
        return parsed
    issues = _dict_items(parsed)
    return {"passed": False, "overall_score": 0.0, "issues": issues}
