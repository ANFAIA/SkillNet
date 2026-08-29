"""The three escalating hints of §7.4, for a Didact activity.

The mirror of ``routes.nodes._hint_for``, which does the same job for a v1 ``QuizItem``,
and it is written as a mirror on purpose: one ladder, three rungs, the same amount
disclosed at each of them, so a learner meets the same rule whichever kind of question is
in front of them.

**Deterministic, and no model call.** A hint is a *disclosure decision*: how much of an
answer key a learner is handed, and when. That has to be reviewable line by line rather
than sampled from a generator that may say more than it was asked to. There are no
authored hints in the data today, so everything here is derived from the two halves the
server already holds — the ``public_definition`` the browser was sent, and the
``evaluation`` inside ``private_definition`` that never leaves.

**The rungs.**

1. Back to the idea of the node. No information about the item at all.
2. A structural nudge that depends on the ``evaluation.mode``: the first element named
   for a ``sequence``, false options ruled out for an ``exact`` choice, the shape of the
   text for a free answer, how many picks a ``set`` takes. The rule of thumb is that rung
   two narrows the search and never closes it.
3. The author's explanation, when there is one. Nothing beyond it: this module never
   returns the answer, because handing the answer over is
   ``activity_solution.render_solution``'s job, behind an entitlement this module has no
   part in deciding.

Every path ends in a sentence — there is no ``None``. A learner who spends a hint must get
something for it, so an activity whose key this module cannot read structurally falls back
to advice about reading the question, and the quota is still spent.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.services.activity_solution import (
    ASSIGNMENT_COLUMNS,
    SINGLE_COLLECTION,
    entry_labels,
    entry_order,
)

#: Rung 1 when the node's summary is unreachable (an archived or deleted node still has
#: activities that can be asked for a hint). Says the same thing without quoting content
#: that is not there to quote.
_NO_SUMMARY = "Vuelve a lo que explica este nodo antes de responder."

#: Rung 2 when the key cannot be read structurally — an adapter-provided mode, a shape
#: this module does not describe, or a collection with nothing labelled in it.
_GENERIC_STRUCTURE = (
    "Relee el enunciado y quédate solo con el dato que decide la respuesta; "
    "lo demás es contexto."
)

#: Rung 3 when the author wrote no explanation.
_GENERIC_EXPLANATION = (
    "Es la respuesta que se sigue directamente de lo que explica el nodo; "
    "compárala con el resumen y decide."
)

#: How many distractors rung 2 may rule out, and the smallest option count that leaves the
#: question worth answering afterwards. Both mirror ``_hint_for``: with three options,
#: discarding two *is* the answer, so the floor is one above the number discarded.
_DISCARDED = 2
_MIN_OPTIONS = _DISCARDED + 1


def _text_shape(value: object) -> str | None:
    """The shape of a written answer: how long it is and how it starts.

    The ``fill_blank`` rung of ``_hint_for``, applied to the free-text modes. It narrows a
    guess without spelling anything: a learner who knows the concept recognises the word,
    a learner who does not still has to produce it.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    answer = value.strip()
    return f"Lo que falta: {len(answer)} caracteres, empieza por '{answer[:1]}'."


def _first_label(collection: Any, ordered_ids: list[str] | None = None) -> str | None:
    """The visible text of the first authored entry, in the order it appears on screen."""
    labels = entry_labels(collection)
    for identifier in ordered_ids if ordered_ids is not None else entry_order(collection):
        label = labels.get(str(identifier))
        if label is not None:
            return label
    return None


def _discard_hint(component_id: str, public: Mapping[str, Any], expected: Any) -> str | None:
    """Two options the learner can cross out, named as they are named on screen."""
    collection = SINGLE_COLLECTION.get(component_id)
    if collection is None:
        return None
    labels = entry_labels(public.get(collection))
    correct = {str(value) for value in (expected if isinstance(expected, list) else [expected])}
    if len(labels) < _MIN_OPTIONS:
        return None
    wrong = [
        labels[identifier]
        for identifier in entry_order(public.get(collection))
        if identifier not in correct and identifier in labels
    ][:_DISCARDED]
    if len(wrong) < _DISCARDED:
        return None
    listed = " y ".join(f'"{label}"' for label in wrong)
    return f"Puedes descartar {listed}."


def _sequence_hint(public: Mapping[str, Any], expected: Any) -> str | None:
    """Name the first step. The same disclosure ``order_steps`` gets on the node ladder."""
    if not isinstance(expected, list) or not expected:
        return None
    label = _first_label(public.get("items"), [str(expected[0])])
    return f'El primer paso es "{label}".' if label else None


def _assignments_hint(component_id: str, public: Mapping[str, Any], expected: Any) -> str | None:
    """Name where to start, never with what.

    A ``sequence`` can afford to give its first element away because the order is the
    answer and one position out of many is a fraction of it. An assignment cannot: the
    pairs are independent, so naming one pair *is* one whole answer. What is safe is the
    left-hand column, which the learner is already looking at — the hint is the advice to
    resolve it one row at a time, starting at the top.
    """
    columns = ASSIGNMENT_COLUMNS.get(component_id)
    if columns is None or not isinstance(expected, Mapping) or not expected:
        return None
    source_key = columns[0]
    ordered = [
        identifier for identifier in entry_order(public.get(source_key)) if identifier in expected
    ]
    label = _first_label(public.get(source_key), ordered)
    if label is None:
        return None
    return f'Resuélvelo de uno en uno y empieza por "{label}": cada elemento tiene una sola pareja.'


def _keyed_text_hint(public: Mapping[str, Any], expected: Any) -> str | None:
    """Name the first gap to fill, not what goes in it."""
    if not isinstance(expected, Mapping) or not expected:
        return None
    ordered = [
        identifier for identifier in entry_order(public.get("steps")) if identifier in expected
    ]
    label = _first_label(public.get("steps"), ordered)
    return f'Empieza por "{label}" y deja los demás huecos para después.' if label else None


def _set_hint(expected: Any) -> str | None:
    """How many picks the answer takes — the mistake this mode produces is the count."""
    if not isinstance(expected, list) or not expected:
        return None
    count = len({str(value) for value in expected})
    if count == 1:
        return "Solo una de las opciones es correcta."
    return f"Son exactamente {count} opciones correctas: ni una más, ni una menos."


def _numeric_hint(public: Mapping[str, Any], evaluation: Mapping[str, Any]) -> str | None:
    """The unit, or the fact that an interval is being asked for. Never the value.

    Tolerances are deliberately absent for the same reason ``render_solution`` does not
    print them: they say how generously the server rounds, which is not something to teach
    a learner to aim at.
    """
    unit = public.get("unit")
    symbol = unit.get("symbol") if isinstance(unit, Mapping) else None
    if isinstance(symbol, str) and symbol.strip():
        return f"La respuesta es un número expresado en {symbol.strip()}; comprueba la unidad."
    if "value" not in evaluation and ("min" in evaluation or "max" in evaluation):
        return "Se acepta un intervalo, no un valor único: comprueba entre qué límites cae."
    return None


def _structure_hint(
    component_id: str, public: Mapping[str, Any], evaluation: Mapping[str, Any]
) -> str | None:
    """Rung 2, dispatched on the mode the key was written in."""
    mode = evaluation.get("mode", "exact")
    expected = evaluation.get("expected")
    if mode == "sequence":
        return _sequence_hint(public, expected)
    if mode == "assignments":
        return _assignments_hint(component_id, public, expected)
    if mode == "keyed_text":
        return _keyed_text_hint(public, expected)
    if mode in {"set", "regions"}:
        return _discard_hint(component_id, public, expected) or _set_hint(expected)
    if mode == "normalized_any":
        first = expected[0] if isinstance(expected, list) and expected else None
        return _text_shape(first)
    if mode == "numeric":
        return _numeric_hint(public, evaluation)
    if mode == "exact":
        # Two different questions wear the same mode: picking one of the options on
        # screen, and typing an answer that is not on screen at all.
        return _discard_hint(component_id, public, expected) or _text_shape(expected)
    return None


def activity_hint(
    level: int,
    *,
    component_id: str,
    public_definition: Mapping[str, Any] | None,
    evaluation: Mapping[str, Any] | None,
    node_summary: str | None,
) -> str:
    """The hint for one rung of the ladder. Always a sentence, never an answer."""
    public: Mapping[str, Any] = public_definition if isinstance(public_definition, Mapping) else {}
    key: Mapping[str, Any] = evaluation if isinstance(evaluation, Mapping) else {}

    if level <= 1:
        summary = node_summary.strip() if isinstance(node_summary, str) else ""
        return f"Vuelve a la idea del nodo: {summary}" if summary else _NO_SUMMARY

    if level == 2:
        return _structure_hint(component_id, public, key) or _GENERIC_STRUCTURE

    explanation = key.get("explanation")
    if isinstance(explanation, str) and explanation.strip():
        return explanation.strip()
    return _GENERIC_EXPLANATION


__all__ = ["activity_hint"]
