"""Adapter between the v2 item shape and the v1 grader.

``grade()`` is **imported verbatim** from ``exercise_service``: it is already a pure
module-level function (``src/services/exercise_service.py``), so it is neither moved
nor modified (§3.4, §13 B5).

An adapter is nonetheless necessary, so this is not "zero new logic": ``grade()``
reads the right answer from a v1 ``content`` dict (``correct``, ``blanks``,
``correct_order``, ``explanation``), while v2 keeps the *statement* in
``QuizItem.props`` and the *solution* in a separate ``answer_key``. Keeping them
apart is the structural equivalent of v1's ``strip_answers()``, but by construction
instead of by filtering: you cannot mis-filter what was never in the same field.

Both directions live here:

* ``content_for(item_props, answer_key_entry)`` -> v1 ``content`` dict, for grading.
* ``split_v1_content(item_type, content, ...)`` -> ``(props, answer_key_entry)``, used
  when sampling existing v1 exercises as probe items (§7.1 source 2). It is the exact
  inverse of ``content_for`` for the four deterministic types, and
  ``tests/test_node_grading.py`` asserts the round trip.

The four deterministic types score **0.0 or 1.0**, with no partial credit — including
``fill_blank``, which returns 0.0 if a single blank is wrong. That is load-bearing for
the arithmetic of §7.2, so nothing here may "make an item continuous".
"""

from __future__ import annotations

import enum
import unicodedata
from typing import Any

from src.core.exceptions import ValidationError
from src.schemas.exercise import AttemptResult

# The one import of the v1 grader. Re-exported so callers need a single import.
from src.services.exercise_service import grade

__all__ = [
    "ANSWER_KEY_FIELDS",
    "classify_error",
    "content_for",
    "grade",
    "grade_item",
    "item_type_of",
    "public_props",
    "split_v1_content",
]

DETERMINISTIC_TYPES = ("test", "true_false", "fill_blank", "order_steps")
OPEN_TYPES = ("practical_case", "dialogue")

# Fields that belong in ``answer_key`` and must never appear in served props.
ANSWER_KEY_FIELDS = (
    "correct",
    "correct_order",
    "blanks",
    "rubric",
    "evaluation_criteria",
    "system_prompt",
    "explanation",
    "max_turns",
)


def _value(raw: object) -> str:
    return raw.value if isinstance(raw, enum.Enum) else str(raw)


def item_type_of(item_props: dict) -> str:
    """The ``exercise_type`` of an item. ``item_type`` is the v2 name; ``type`` is
    accepted because that is what a v1 exercise row calls it."""
    raw = item_props.get("item_type") or item_props.get("type")
    if not raw:
        raise ValidationError("Item has no item_type", field="item_type")
    return _value(raw)


def _first(*candidates: Any) -> Any:
    for candidate in candidates:
        if candidate is not None:
            return candidate
    return None


def content_for(item_props: dict, answer_key_entry: dict | None = None) -> dict:
    """Recombine v2 props + answer key into the v1 ``content`` dict ``grade()`` expects.

    ``answer_key_entry`` is the entry of ``node_renders.answer_key`` /
    ``node_probes.answer_key`` for this ``item_id``. When it is ``None`` (an item
    served without its key) the returned content has no solution, so every
    deterministic type scores 0.0 — a missing key can never accidentally pass.
    """
    key = answer_key_entry or {}
    item_type = item_type_of(item_props)
    explanation = _first(key.get("explanation"), item_props.get("explanation"))

    if item_type == "test":
        return {
            "question": item_props.get("question", ""),
            "options": list(item_props.get("options") or []),
            "correct": key.get("correct"),
            "explanation": explanation,
        }

    if item_type == "true_false":
        # v1 calls it `statement`; the v2 QuizItem prop is `question`.
        return {
            "statement": _first(item_props.get("statement"), item_props.get("question")) or "",
            "correct": key.get("correct"),
            "explanation": explanation,
        }

    if item_type == "fill_blank":
        return {
            "template": _first(item_props.get("template"), item_props.get("question")) or "",
            "blanks": list(key.get("blanks") or []),
            "explanation": explanation,
        }

    if item_type == "order_steps":
        return {
            "instruction": _first(item_props.get("instruction"), item_props.get("question")) or "",
            "steps": list(_first(item_props.get("steps"), item_props.get("options")) or []),
            "correct_order": list(key.get("correct_order") or []),
            "explanation": explanation,
        }

    if item_type == "practical_case":
        return {
            "context": item_props.get("context", ""),
            "question": item_props.get("question", ""),
            "rubric": list(key.get("rubric") or []),
            "explanation": explanation,
        }

    if item_type == "dialogue":
        return {
            "context": item_props.get("context", ""),
            "system_prompt": key.get("system_prompt", ""),
            "max_turns": key.get("max_turns", 6),
            "evaluation_criteria": list(key.get("evaluation_criteria") or []),
        }

    raise ValidationError(f"Unknown item type: {item_type}", field="item_type")


def split_v1_content(
    item_type: object,
    content: dict,
    *,
    item_id: str,
    bloom_level: str | None = None,
) -> tuple[dict, dict]:
    """Inverse of :func:`content_for`: v1 ``content`` -> ``(props, answer_key_entry)``.

    Used to reuse existing v1 exercises as probe items (§7.1 source 2, zero tokens).
    The props are already answer-free, so they are safe to serve.
    """
    kind = _value(item_type)
    props: dict[str, Any] = {"item_id": item_id, "item_type": kind}
    if bloom_level:
        props["bloom_level"] = bloom_level
    key: dict[str, Any] = {}
    if content.get("explanation") is not None:
        key["explanation"] = content["explanation"]

    if kind == "test":
        props["question"] = content.get("question", "")
        props["options"] = list(content.get("options") or [])
        key["correct"] = content.get("correct")
    elif kind == "true_false":
        props["question"] = content.get("statement", "")
        props["statement"] = content.get("statement", "")
        key["correct"] = content.get("correct")
    elif kind == "fill_blank":
        props["template"] = content.get("template", "")
        key["blanks"] = list(content.get("blanks") or [])
    elif kind == "order_steps":
        props["instruction"] = content.get("instruction", "")
        props["steps"] = list(content.get("steps") or [])
        key["correct_order"] = list(content.get("correct_order") or [])
    elif kind == "practical_case":
        props["context"] = content.get("context", "")
        props["question"] = content.get("question", "")
        key["rubric"] = list(content.get("rubric") or [])
    elif kind == "dialogue":
        props["context"] = content.get("context", "")
        key["system_prompt"] = content.get("system_prompt", "")
        key["max_turns"] = content.get("max_turns", 6)
        key["evaluation_criteria"] = list(content.get("evaluation_criteria") or [])
    else:
        raise ValidationError(f"Unknown item type: {kind}", field="item_type")

    return props, key


def public_props(item_props: dict) -> dict:
    """Belt over braces: drop any answer-revealing field from props before serving.

    The answer lives in a different column, so this should always be a no-op; it is
    here so that a generator that misplaces ``correct`` cannot leak it.
    """
    return {k: v for k, v in item_props.items() if k not in ANSWER_KEY_FIELDS}


def grade_item(
    item_props: dict,
    answer_key_entry: dict | None,
    answer: Any,
) -> AttemptResult:
    """Grade one v2 item with the v1 grader. Deterministic and LLM-free.

    Open types (``practical_case``, ``dialogue``) fall back to ``grade()``'s
    LLM-free result; the caller passes them through ``grade_open_answer`` when an
    eval-purpose LLM is available (§3.4).
    """
    item_type = item_type_of(item_props)
    return grade(item_type, content_for(item_props, answer_key_entry), answer)


# --- §7.4 error classification ----------------------------------------------


def _normalize(text: Any) -> str:
    """Casefold, strip accents and strip non-alphanumerics — the "same answer,
    typed differently" test."""
    decomposed = unicodedata.normalize("NFKD", str(text))
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return "".join(ch for ch in stripped.casefold() if ch.isalnum())


def classify_error(
    item_props: dict,
    answer_key_entry: dict | None,
    answer: Any,
) -> str:
    """``detail`` | ``procedural`` | ``conceptual`` for ``last_error_kind`` (§7.4).

    Deterministic, and only ever called on a failure:

    * ``detail`` — the content is right and only the form is wrong (typo, accent,
      casing, punctuation). Only reachable for ``fill_blank``, the one type with a
      free-text answer.
    * ``procedural`` — the right pieces in the wrong place: ``order_steps`` with the
      right set of steps in the wrong order, or ``fill_blank`` with the blanks swapped.
    * ``conceptual`` — anything else, which is the honest default: a wrong option in a
      4-choice item tells you the *what* was wrong, not the *how*.
    """
    key = answer_key_entry or {}
    item_type = item_type_of(item_props)

    if item_type == "fill_blank":
        expected = [_normalize(v) for v in (key.get("blanks") or [])]
        given_raw = answer.get("answers") if isinstance(answer, dict) else answer
        if not isinstance(given_raw, list) or len(given_raw) != len(expected):
            return "conceptual"
        given = [_normalize(v) for v in given_raw]
        if given == expected:
            return "detail"  # only case/accents/punctuation differed
        if sorted(given) == sorted(expected):
            return "procedural"  # right values, wrong slots
        return "conceptual"

    if item_type == "order_steps":
        expected_order = list(key.get("correct_order") or [])
        given_order = answer.get("order") if isinstance(answer, dict) else answer
        if isinstance(given_order, list) and sorted(given_order) == sorted(expected_order):
            return "procedural"  # same steps, wrong sequence
        return "conceptual"

    return "conceptual"
