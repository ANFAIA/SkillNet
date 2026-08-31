"""The three escalating hints of §7.4, and the words both ladders say them in.

This module owns **both** ladders' vocabulary. :func:`activity_hint` walks a Didact
activity, and the rung phrasings it uses are exported so that ``routes.nodes._hint_for`` —
the same ladder for a v1 ``QuizItem`` — says them with the same words instead of its own
copy. Until 2026-08-31 there were two copies and they had already drifted: the same
sentence lived here with accents and there without, and rung 3's fallback said "la
respuesta que se sigue de lo que explica el nodo" on one side and "la opcion que se sigue
de la regla del nodo" on the other. A learner met a different rule depending on which kind
of question was in front of them, which is precisely what writing one as a mirror of the
other was meant to prevent (`CLAUDE.md` §5).

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

**Language.** A hint is text a learner reads, so it needs the second language as much as
the lesson does, and no prompt can supply it: nothing here calls a model. One table per
language and a lookup, which is what fourteen sentences are worth — an i18n framework in
the backend would be more machinery than there is text to translate. The caller resolves
the language (``src/services/language_policy.py``); an unrecognised value falls back to the
default, because a hint that raises is worse than a hint in the wrong language.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from src.core.language import DEFAULT_LANGUAGE, Language, normalize_language
from src.services.activity_solution import (
    ASSIGNMENT_COLUMNS,
    SINGLE_COLLECTION,
    entry_labels,
    entry_order,
)

#: Every sentence either ladder can produce. Keyed by the *situation* rather than by the
#: text, so a re-wording never reaches a call site.
#:
#: ``no_summary`` is rung 1 when the node's summary is unreachable (an archived or deleted
#: node still has activities that can be asked for a hint): it says the same thing without
#: quoting content that is not there to quote. ``generic_structure`` is rung 2 when the key
#: cannot be read structurally — an adapter-provided mode, a shape this module does not
#: describe, or a collection with nothing labelled in it. ``generic_explanation`` is rung 3
#: when the author wrote no explanation.
_PHRASES: dict[Language, dict[str, str]] = {
    "es": {
        "no_summary": "Vuelve a lo que explica este nodo antes de responder.",
        "back_to_node": "Vuelve a la idea del nodo: {summary}",
        "generic_structure": (
            "Relee el enunciado y quédate solo con el dato que decide la respuesta; "
            "lo demás es contexto."
        ),
        "generic_explanation": (
            "Es la respuesta que se sigue directamente de lo que explica el nodo; "
            "compárala con el resumen y decide."
        ),
        "discard": "Puedes descartar {options}.",
        "and": " y ",
        "first_step": 'El primer paso es "{label}".',
        "missing": "Lo que falta: {shape}.",
        "missing_part": "{length} caracteres, empieza por '{initial}'",
        "one_pair_at_a_time": (
            'Resuélvelo de uno en uno y empieza por "{label}": cada elemento tiene una '
            "sola pareja."
        ),
        "first_gap": 'Empieza por "{label}" y deja los demás huecos para después.',
        "one_correct": "Solo una de las opciones es correcta.",
        "n_correct": (
            "Son exactamente {count} opciones correctas: ni una más, ni una menos."
        ),
        "numeric_unit": (
            "La respuesta es un número expresado en {symbol}; comprueba la unidad."
        ),
        "numeric_interval": (
            "Se acepta un intervalo, no un valor único: comprueba entre qué límites cae."
        ),
    },
    "en": {
        "no_summary": "Go back over what this lesson explains before answering.",
        "back_to_node": "Back to the idea of the lesson: {summary}",
        "generic_structure": (
            "Read the question again and keep only the fact that decides the answer; "
            "the rest is context."
        ),
        "generic_explanation": (
            "It is the answer that follows directly from what the lesson explains; "
            "compare it with the summary and decide."
        ),
        "discard": "You can rule out {options}.",
        "and": " and ",
        "first_step": 'The first step is "{label}".',
        "missing": "What is missing: {shape}.",
        "missing_part": "{length} characters, starts with '{initial}'",
        "one_pair_at_a_time": (
            'Work through it one at a time and start with "{label}": each element has '
            "exactly one match."
        ),
        "first_gap": 'Start with "{label}" and leave the other gaps for later.',
        "one_correct": "Only one of the options is correct.",
        "n_correct": "Exactly {count} options are correct: no more, no fewer.",
        "numeric_unit": "The answer is a number expressed in {symbol}; check the unit.",
        "numeric_interval": (
            "A range is accepted, not a single value: check which limits it falls between."
        ),
    },
}

#: How many distractors rung 2 may rule out, and the smallest option count that leaves the
#: question worth answering afterwards. With three options, discarding two *is* the answer,
#: so the floor is one above the number discarded.
_DISCARDED = 2
_MIN_OPTIONS = _DISCARDED + 1


def _phrases(language: str | None) -> dict[str, str]:
    return _PHRASES[normalize_language(language) or DEFAULT_LANGUAGE]


# --------------------------------------------------------------------------------------
# The rung phrasings. Public because the ``QuizItem`` ladder in ``routes.nodes`` says the
# same sentences about a differently shaped item, and one of the two has to own the words.
# --------------------------------------------------------------------------------------
def back_to_node(summary: str | None, language: str | None = None) -> str:
    """Rung 1: point at the idea of the node, or at the node when it has no summary."""
    words = _phrases(language)
    text = summary.strip() if isinstance(summary, str) else ""
    return words["back_to_node"].format(summary=text) if text else words["no_summary"]


def discard_options(labels: Sequence[str], language: str | None = None) -> str:
    """Rung 2 for a choice: name the options the learner can cross out."""
    words = _phrases(language)
    listed = words["and"].join(f'"{label}"' for label in labels)
    return words["discard"].format(options=listed)


def first_step(label: str, language: str | None = None) -> str:
    """Rung 2 for an ordering: name where the sequence starts."""
    return _phrases(language)["first_step"].format(label=label)


def missing_text(parts: Sequence[tuple[int, str]], language: str | None = None) -> str:
    """Rung 2 for a written answer: how long each gap is and how it starts.

    Takes ``(length, initial)`` pairs rather than the answers themselves, so no caller can
    hand the whole word to a function whose entire job is to withhold it.
    """
    words = _phrases(language)
    shape = ", ".join(
        words["missing_part"].format(length=length, initial=initial)
        for length, initial in parts
    )
    return words["missing"].format(shape=shape)


def generic_structure(language: str | None = None) -> str:
    """Rung 2 when the key cannot be read structurally."""
    return _phrases(language)["generic_structure"]


def generic_explanation(language: str | None = None) -> str:
    """Rung 3 when the author wrote no explanation."""
    return _phrases(language)["generic_explanation"]


# --------------------------------------------------------------------------------------
# The Didact ladder
# --------------------------------------------------------------------------------------
def _text_shape(value: object, language: str | None) -> str | None:
    """The shape of a written answer: how long it is and how it starts.

    The ``fill_blank`` rung of ``_hint_for``, applied to the free-text modes. It narrows a
    guess without spelling anything: a learner who knows the concept recognises the word,
    a learner who does not still has to produce it.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    answer = value.strip()
    return missing_text([(len(answer), answer[:1])], language)


def _first_label(collection: Any, ordered_ids: list[str] | None = None) -> str | None:
    """The visible text of the first authored entry, in the order it appears on screen."""
    labels = entry_labels(collection)
    for identifier in ordered_ids if ordered_ids is not None else entry_order(collection):
        label = labels.get(str(identifier))
        if label is not None:
            return label
    return None


def _discard_hint(
    component_id: str,
    public: Mapping[str, Any],
    expected: Any,
    language: str | None,
) -> str | None:
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
    return discard_options(wrong, language)


def _sequence_hint(
    public: Mapping[str, Any], expected: Any, language: str | None
) -> str | None:
    """Name the first step. The same disclosure ``order_steps`` gets on the node ladder."""
    if not isinstance(expected, list) or not expected:
        return None
    label = _first_label(public.get("items"), [str(expected[0])])
    return first_step(label, language) if label else None


def _assignments_hint(
    component_id: str,
    public: Mapping[str, Any],
    expected: Any,
    language: str | None,
) -> str | None:
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
    return _phrases(language)["one_pair_at_a_time"].format(label=label)


def _keyed_text_hint(
    public: Mapping[str, Any], expected: Any, language: str | None
) -> str | None:
    """Name the first gap to fill, not what goes in it."""
    if not isinstance(expected, Mapping) or not expected:
        return None
    ordered = [
        identifier for identifier in entry_order(public.get("steps")) if identifier in expected
    ]
    label = _first_label(public.get("steps"), ordered)
    if label is None:
        return None
    return _phrases(language)["first_gap"].format(label=label)


def _set_hint(expected: Any, language: str | None) -> str | None:
    """How many picks the answer takes — the mistake this mode produces is the count."""
    if not isinstance(expected, list) or not expected:
        return None
    words = _phrases(language)
    count = len({str(value) for value in expected})
    if count == 1:
        return words["one_correct"]
    return words["n_correct"].format(count=count)


def _numeric_hint(
    public: Mapping[str, Any], evaluation: Mapping[str, Any], language: str | None
) -> str | None:
    """The unit, or the fact that an interval is being asked for. Never the value.

    Tolerances are deliberately absent for the same reason ``render_solution`` does not
    print them: they say how generously the server rounds, which is not something to teach
    a learner to aim at.
    """
    words = _phrases(language)
    unit = public.get("unit")
    symbol = unit.get("symbol") if isinstance(unit, Mapping) else None
    if isinstance(symbol, str) and symbol.strip():
        return words["numeric_unit"].format(symbol=symbol.strip())
    if "value" not in evaluation and ("min" in evaluation or "max" in evaluation):
        return words["numeric_interval"]
    return None


def _structure_hint(
    component_id: str,
    public: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    language: str | None,
) -> str | None:
    """Rung 2, dispatched on the mode the key was written in."""
    mode = evaluation.get("mode", "exact")
    expected = evaluation.get("expected")
    if mode == "sequence":
        return _sequence_hint(public, expected, language)
    if mode == "assignments":
        return _assignments_hint(component_id, public, expected, language)
    if mode == "keyed_text":
        return _keyed_text_hint(public, expected, language)
    if mode in {"set", "regions"}:
        return _discard_hint(component_id, public, expected, language) or _set_hint(
            expected, language
        )
    if mode == "normalized_any":
        first = expected[0] if isinstance(expected, list) and expected else None
        return _text_shape(first, language)
    if mode == "numeric":
        return _numeric_hint(public, evaluation, language)
    if mode == "exact":
        # Two different questions wear the same mode: picking one of the options on
        # screen, and typing an answer that is not on screen at all.
        return _discard_hint(component_id, public, expected, language) or _text_shape(
            expected, language
        )
    return None


def activity_hint(
    level: int,
    *,
    component_id: str,
    public_definition: Mapping[str, Any] | None,
    evaluation: Mapping[str, Any] | None,
    node_summary: str | None,
    language: str | None = None,
) -> str:
    """The hint for one rung of the ladder. Always a sentence, never an answer."""
    public: Mapping[str, Any] = public_definition if isinstance(public_definition, Mapping) else {}
    key: Mapping[str, Any] = evaluation if isinstance(evaluation, Mapping) else {}

    if level <= 1:
        return back_to_node(node_summary, language)

    if level == 2:
        return _structure_hint(
            component_id, public, key, language
        ) or generic_structure(language)

    explanation = key.get("explanation")
    if isinstance(explanation, str) and explanation.strip():
        return explanation.strip()
    return generic_explanation(language)


__all__ = [
    "activity_hint",
    "back_to_node",
    "discard_options",
    "first_step",
    "generic_explanation",
    "generic_structure",
    "missing_text",
]
