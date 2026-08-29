"""Project a server-owned answer key into the one line a learner may be shown.

Everything here is **pure**: no session, no clock, no LLM, same discipline as
``mastery_service``. It takes the two halves the server holds — the ``public_definition``
that was already sent to the browser and the ``private_definition.evaluation`` that never
leaves — and returns a *rendered* projection, or ``None``.

**Why the server has to do this.** ``evaluation.expected`` of a ``didact.matching`` is
``{"source-1": "target-1"}``: machine ids that mean nothing on screen. Turning them into
"Concepto A -> Definición A" needs ``public_definition.sources`` and ``.targets`` as well,
and only the server holds both. Shipping ``expected`` to the client instead would be
handing over the key.

**What may cross.** The rendered text and, when the author wrote one, the explanation.
Never the raw ``expected``, and never ``private_definition`` itself — it also carries
simulations and rubrics. The shape mirrors ``nodes._correct_answer``, which does the same
job for a v1 ``QuizItem``; there is deliberately no second vocabulary for this.

**When it returns ``None``.** A mode this module cannot render honestly, a key that
references ids the public half does not describe, an entry with no human-readable label.
Callers must treat ``None`` as "nothing to show", never as "keep the learner here":
unblocking is ``Transition.show_worked_solution``'s job and is decided without ever
consulting this module.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - annotation only, keeps this module session-free
    from src.models.activity_definition import ActivityDefinition

#: The two ordered collections whose ids an ``assignments`` key maps between, per
#: component. Left is the key's *keys*, right is its *values* — the direction differs
#: between components (``didact.label-diagram`` maps target -> label, the others map
#: prompt -> answer), which is exactly why this cannot be inferred.
_ASSIGNMENT_COLUMNS: Mapping[str, tuple[str, str]] = {
    "didact.matching": ("sources", "targets"),
    "didact.categorize": ("items", "categories"),
    "didact.word-bank": ("gaps", "options"),
    "didact.label-diagram": ("targets", "items"),
}

#: Where the labels of a single-collection mode live.
_SINGLE_COLLECTION: Mapping[str, str] = {
    "didact.sort": "items",
    "didact.quiz.single-choice": "options",
    "didact.quiz.multi-select": "options",
    "didact.hotspot": "regions",
}

#: Keys that may carry an entry's visible text, most specific first. ``value``/``id`` are
#: never among them: a machine id on screen is the bug this module exists to prevent.
_LABEL_KEYS = ("content", "label", "text", "prompt", "title")

#: Keys that may carry an entry's identifier, in the order the Didact contracts use them.
_IDENTIFIER_KEYS = ("id", "value")

#: The two words a ``didact.quiz.true-false`` answer can be. There is no authored label to
#: read for this component (its public half is one ``question`` and nothing else), so the
#: copy is fixed here to match what ``SecureEvaluatedActivity`` already paints on its two
#: radio buttons. Emitting ``"true"``/``"false"`` instead would put a JSON literal in front
#: of a learner.
_BOOLEAN_TEXT = {True: "Verdadero", False: "Falso"}

#: Joins the two halves of one assignment. A glyph, not a word, so it needs no translating.
_PAIR_ARROW = " → "

#: Stands in for the hole in a ``didact.word-bank`` gap that has no prompt of its own.
_GAP_PLACEHOLDER = "___"


def _entries(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, Mapping)]


def _identifier(entry: Mapping[str, Any]) -> str | None:
    for key in _IDENTIFIER_KEYS:
        raw = entry.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def _label(entry: Mapping[str, Any]) -> str | None:
    """The visible text of one authored entry, or ``None`` when it has none.

    The ``before``/``after`` fallback is for ``didact.word-bank`` gaps, whose text is the
    sentence *around* the hole; rebuilding it with a placeholder is what makes
    "El proceso ___ del ciclo → fase inicial" readable instead of "gap-1 → fase inicial".
    """
    for key in _LABEL_KEYS:
        raw = entry.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    around: list[str] = []
    for key in ("before", "after"):
        raw = entry.get(key)
        if isinstance(raw, str) and raw.strip():
            around.append(raw.strip())
    if not around:
        return None
    if len(around) == 1:
        return f"{around[0]} {_GAP_PLACEHOLDER}"
    return f"{around[0]} {_GAP_PLACEHOLDER} {around[1]}"


def _labels(value: Any) -> dict[str, str]:
    """``id -> visible text`` for one authored collection. Unlabelled entries are dropped."""
    projected: dict[str, str] = {}
    for entry in _entries(value):
        identifier = _identifier(entry)
        label = _label(entry)
        if identifier is not None and label is not None:
            projected[identifier] = label
    return projected


def _order(value: Any) -> list[str]:
    """The authored order of a collection's ids, so the projection reads like the screen."""
    return [
        identifier
        for entry in _entries(value)
        if (identifier := _identifier(entry)) is not None
    ]


def _number_text(value: Any) -> str | None:
    """A number as an author would write it: ``10``, not ``10.0``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, int) or float(value).is_integer():
        return str(int(value))
    return f"{value:g}"


def _first_accepted(value: Any) -> str | None:
    """The canonical answer of an *any-of* key: the first variant the author listed.

    ``normalized_any`` and ``keyed_text`` list synonyms so grading forgives wording. Only
    the first is shown — reciting every accepted spelling teaches the learner nothing and
    reads as a list of near-duplicates.
    """
    candidates = value if isinstance(value, list) else [value]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _lines(values: Iterable[str]) -> str | None:
    joined = "\n".join(values)
    return joined or None


def _assignments_text(
    component_id: str, public: Mapping[str, Any], expected: Any
) -> str | None:
    columns = _ASSIGNMENT_COLUMNS.get(component_id)
    if columns is None or not isinstance(expected, Mapping) or not expected:
        return None
    source_key, target_key = columns
    sources = _labels(public.get(source_key))
    targets = _labels(public.get(target_key)) if target_key else {}
    rendered: list[str] = []
    for source_id in _order(public.get(source_key)):
        if source_id not in expected:
            continue
        left = sources.get(source_id)
        right = targets.get(str(expected[source_id]))
        if left is None or right is None:
            return None
        rendered.append(f"{left}{_PAIR_ARROW}{right}")
    # Every key of the answer has to be accounted for, or the learner is shown a partial
    # solution that looks complete.
    if len(rendered) != len(expected):
        return None
    return _lines(rendered)


def _keyed_text_text(public: Mapping[str, Any], expected: Any) -> str | None:
    """``didact.completion-problem``: each missing step paired with its accepted answer."""
    if not isinstance(expected, Mapping) or not expected:
        return None
    prompts = _labels(public.get("steps"))
    rendered: list[str] = []
    for step_id in _order(public.get("steps")):
        if step_id not in expected:
            continue
        prompt = prompts.get(step_id)
        answer = _first_accepted(expected[step_id])
        if prompt is None or answer is None:
            return None
        rendered.append(f"{prompt}{_PAIR_ARROW}{answer}")
    if len(rendered) != len(expected):
        return None
    return _lines(rendered)


def _sequence_text(public: Mapping[str, Any], expected: Any) -> str | None:
    """``didact.sort``: the ordered steps, numbered, because the order *is* the answer."""
    if not isinstance(expected, list) or not expected:
        return None
    labels = _labels(public.get("items"))
    rendered: list[str] = []
    for position, item_id in enumerate(expected, start=1):
        label = labels.get(str(item_id))
        if label is None:
            return None
        rendered.append(f"{position}. {label}")
    return _lines(rendered)


def _choice_text(component_id: str, public: Mapping[str, Any], expected: Any) -> str | None:
    """One or more selected options, rendered by their authored labels."""
    collection = _SINGLE_COLLECTION.get(component_id)
    if collection is None:
        return None
    labels = _labels(public.get(collection))
    selected = expected if isinstance(expected, list) else [expected]
    if not selected:
        return None
    rendered = [labels.get(str(value)) for value in selected]
    if any(label is None for label in rendered):
        return None
    return _lines(label for label in rendered if label is not None)


def _exact_text(component_id: str, public: Mapping[str, Any], expected: Any) -> str | None:
    if isinstance(expected, bool):
        return _BOOLEAN_TEXT[expected]
    if component_id in _SINGLE_COLLECTION:
        return _choice_text(component_id, public, expected)
    if isinstance(expected, str) and expected.strip():
        return expected.strip()
    return _number_text(expected)


def _numeric_text(public: Mapping[str, Any], evaluation: Mapping[str, Any]) -> str | None:
    """A value, or the range that was accepted. Tolerances are grading, not the answer.

    ``absolute_tolerance``/``relative_tolerance`` are deliberately not printed: they say how
    generously the server rounds, which is not something a learner should be taught to aim
    at. A range *is* printed, because there the interval is the answer.
    """
    unit = public.get("unit")
    symbol = unit.get("symbol") if isinstance(unit, Mapping) else None
    suffix = f" {symbol.strip()}" if isinstance(symbol, str) and symbol.strip() else ""
    if "value" in evaluation:
        value = _number_text(evaluation["value"])
        return f"{value}{suffix}" if value is not None else None
    low = _number_text(evaluation.get("min"))
    high = _number_text(evaluation.get("max"))
    if low is not None and high is not None:
        return f"{low} – {high}{suffix}"
    if low is not None:
        return f"≥ {low}{suffix}"
    if high is not None:
        return f"≤ {high}{suffix}"
    return None


def _explanation(evaluation: Mapping[str, Any]) -> str | None:
    """The author's justification, which lives inside the private key with the answer.

    Read from ``evaluation`` and nowhere else: anything an author put in the *public* half
    the client already has, so surfacing it again here would only duplicate it.
    """
    raw = evaluation.get("explanation")
    return raw.strip() if isinstance(raw, str) and raw.strip() else None


def render_solution(
    *,
    component_id: str,
    public_definition: Mapping[str, Any] | None,
    evaluation: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """The revealable projection of one answer key, or ``None`` if it cannot be rendered.

    Returns ``{"solution": str, "explanation": str | None}``. ``solution`` is always
    non-empty text a learner can read; multi-part answers are one line per part.
    """
    if not isinstance(evaluation, Mapping):
        return None
    public: Mapping[str, Any] = public_definition if isinstance(public_definition, Mapping) else {}
    mode = evaluation.get("mode", "exact")
    expected = evaluation.get("expected")

    if mode == "assignments":
        text = _assignments_text(component_id, public, expected)
    elif mode == "sequence":
        text = _sequence_text(public, expected)
    elif mode == "keyed_text":
        text = _keyed_text_text(public, expected)
    elif mode == "exact":
        text = _exact_text(component_id, public, expected)
    elif mode in {"set", "regions"}:
        text = _choice_text(component_id, public, expected)
    elif mode == "normalized_any":
        text = _first_accepted(expected)
    elif mode == "numeric":
        text = _numeric_text(public, evaluation)
    else:
        # An adapter-provided or future mode. Silence is the honest answer; the learner is
        # unblocked by rule 8 either way.
        text = None

    if not text:
        return None
    return {"solution": text, "explanation": _explanation(evaluation)}


def revealed_solution(
    activity: "ActivityDefinition", *, passed: bool, show_worked_solution: bool
) -> dict[str, Any] | None:
    """The worked solution, only once the learner is entitled to see it.

    One function because there is one entitlement. ``POST /activities/{id}/evaluate`` and
    ``POST /activities/{id}/attempts`` grade the same activities for the same learners, and
    a second copy of the gate is a second chance to drift: for a while ``/attempts``
    announced ``show_worked_solution: true`` while sending no ``solution`` at all, which the
    client reads as "closed, here is the answer" — retry button gone, panel empty, no way
    back. The gate lives here so both routes cannot disagree about it.

    ``passed or show_worked_solution`` mirrors the gate ``POST /nodes/{id}/answer`` puts in
    front of ``correct_answer``. It deliberately does **not** include the node's spent hint
    quota: ``learner_node_states.hints_used`` is a whole-node counter, so reading it here
    would unlock the answer to every remaining activity in the node the moment three hints
    were spent anywhere in it.

    Returns ``None`` both when the learner is not entitled *and* when
    :func:`render_solution` cannot render the mode honestly. Those two are indistinguishable
    to the caller on purpose — neither is a reason to keep the learner in place — so
    ``show_worked_solution: true`` alongside ``solution: null`` is a valid, reachable
    response. A client must decide its copy by looking at ``solution``, not at the flag.
    """
    if not (passed or show_worked_solution):
        return None
    return render_solution(
        component_id=activity.component_id,
        public_definition=activity.public_definition,
        evaluation=(activity.private_definition or {}).get("evaluation"),
    )


__all__ = ["render_solution", "revealed_solution"]
