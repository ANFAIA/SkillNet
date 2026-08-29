"""Business rules shared by all declarative Didact activity families."""

from __future__ import annotations

import hmac
import logging
import math
import re
import unicodedata
import uuid
from collections.abc import Mapping
from typing import Any

from src.core.exceptions import ConflictError, NotFoundError, ValidationError
from src.models.activity_definition import ActivityDefinition
from src.repositories.activity_definition_repo import (
    ActivityDefinitionRepository,
    ActivityStateRepository,
)
from src.schemas.activity import ActivityDefinitionCreate
from src.services.activity_ports import ActivityPortRegistry, PortDeclined

logger = logging.getLogger(__name__)

BUILTIN_PORTS = frozenset({"assets", "evaluation", "persistence", "progress", "simulation"})
BUILTIN_EVALUATION_VERSION = "activity-definition-evaluation/1"
BUILTIN_EVALUATION_MODES = frozenset(
    {
        "exact",
        "normalized_any",
        "set",
        "regions",
        "assignments",
        "sequence",
        "keyed_text",
        "numeric",
    }
)

#: Declines that mean **the activity is defective**, not that the submission was wrong.
#:
#: Both are generation defects: the authoring step persisted an activity whose answer key
#: is missing or written in a mode the built-in scorer does not implement. The learner can
#: never pass it, and — before this set existed — could never accumulate a countable
#: failure either, so rule 8 of §7.3 never fired and the node stayed shut. Callers that
#: serve a learner must treat these as "let them through now", and they are logged because
#: nothing else makes them visible.
BROKEN_EVALUATION_REASONS = frozenset(
    {"missing_evaluation_definition", "unsupported_evaluation_mode"}
)


#: Glyphs a phone keyboard or an office autocorrect substitutes without asking, folded to the
#: ASCII twin the learner meant to type. Only quotes and apostrophes: dashes are left alone
#: because a hyphen inside a term ("coste-beneficio") is spelling, not typography.
_ASCII_QUOTES = str.maketrans(
    {
        "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
        "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
        "«": '"', "»": '"',
    }
)
#: Sentence framing, not answer content: a learner who closes with a period, or wraps the
#: answer in Spanish question marks, wrote the same answer. Stripped only at the edges, so
#: "3.14" and "etc." keep their insides.
_OPENING_PUNCTUATION = "¿¡"
_CLOSING_PUNCTUATION = ".,;:!?…"
#: Written as an escape on purpose: a bare combining mark in source is invisible.
_COMBINING_TILDE = "\u0303"


def _fold_diacritics(text: str) -> str:
    """Drop combining marks (Unicode category ``Mn``), keeping the tilde that spells ``ñ``."""

    kept: list[str] = []
    for char in unicodedata.normalize("NFKD", text):
        if unicodedata.category(char) != "Mn":
            kept.append(char)
        elif char == _COMBINING_TILDE and kept and kept[-1] in "nN":
            kept.append(char)
    return unicodedata.normalize("NFC", "".join(kept))


def _normalized_text(value: object, *, case_sensitive: bool = False) -> str:
    """Normalize one answer so grading measures knowledge instead of typing.

    Whitespace runs collapse, curly quotes and apostrophes fold to their ASCII twins, and
    sentence-framing punctuation at the edges is dropped. Those three apply in both modes:
    which glyph the keyboard produced, and whether the learner closed with a period, is
    never what the activity is testing -- not even when the author asked for exact spelling.

    With ``case_sensitive`` false (the default, and what ``didact.quiz.fill-in-the-blank``
    and ``didact.quiz.short-answer`` use) the text is also case-folded and its diacritics
    are removed. Two product decisions are baked into that, both of them Spanish-specific:

    * **``ñ`` survives.** It is a letter of the Spanish alphabet, not an ``n`` wearing an
      accent, and the pairs it separates are real different words: ``año``/``ano``,
      ``caña``/``cana``, ``seña``/``sena``. Folding every combining mark blindly would make
      ``ano`` a correct answer for ``año``, which is both wrong and embarrassing to show a
      learner. So the combining tilde is kept when it sits on an ``n``, and the result is
      recomposed with NFC so ``ñ`` written either way compares equal.
    * **Every other mark goes, the diaeresis included.** ``ü`` only records that the ``u``
      of ``pingüino`` is pronounced; Spanish has no pair of words told apart by a diaeresis,
      so ``pinguino`` is a typo, never a different answer. The acute accent is folded for a
      weaker but deliberate reason: pairs like ``esta``/``está`` do exist, yet the question
      already fixes which word is meant, and failing an answer over a missing accent grades
      the keyboard layout, not the learning. The cost we accept is that an activity cannot
      use these modes to test accentuation itself; ``case_sensitive: true`` is that opt-out.

    With ``case_sensitive`` true nothing is folded: only NFC runs, so a precomposed ``ó``
    equals an ``o`` followed by a combining acute accent -- two encodings of one character,
    which no author means to distinguish.
    """

    text = " ".join(str(value).translate(_ASCII_QUOTES).split())
    text = text.lstrip(_OPENING_PUNCTUATION).rstrip(_CLOSING_PUNCTUATION).strip()
    if case_sensitive:
        return unicodedata.normalize("NFC", text)
    return _fold_diacritics(text.casefold())


def _texts_match(candidate: object, answer: object) -> bool:
    """Constant-time equality for two already-normalized answers.

    ``hmac.compare_digest`` refuses ``str`` arguments that hold non-ASCII characters, so a
    normalized Spanish answer that still carries an ``ñ`` would raise ``TypeError`` instead
    of scoring. Comparing the UTF-8 encoding keeps the constant-time guarantee and accepts
    the whole alphabet.
    """

    return hmac.compare_digest(str(candidate).encode("utf-8"), str(answer).encode("utf-8"))


def _score_assignments(received: object, expected: object) -> float | None:
    if not isinstance(received, dict) or not isinstance(expected, dict) or not expected:
        return None
    return sum(
        _texts_match(received.get(key, ""), answer)
        for key, answer in expected.items()
    ) / len(expected)


def _score_sequence(received: object, expected: object) -> float | None:
    if not isinstance(received, list) or not isinstance(expected, list) or not expected:
        return None
    if len(received) != len(expected):
        return 0.0
    return sum(
        _texts_match(actual, answer)
        for actual, answer in zip(received, expected, strict=True)
    ) / len(expected)


def _score_keyed_text(received: object, expected: object, *, case_sensitive: bool) -> float | None:
    if not isinstance(received, dict) or not isinstance(expected, dict) or not expected:
        return None
    correct = 0
    for key, accepted in expected.items():
        answers = accepted if isinstance(accepted, list) else [accepted]
        candidate = _normalized_text(received.get(key, ""), case_sensitive=case_sensitive)
        correct += any(
            _texts_match(
                candidate,
                _normalized_text(answer, case_sensitive=case_sensitive),
            )
            for answer in answers
        )
    return correct / len(expected)


def _score_numeric(received: object, config: dict) -> float | None:
    raw = str(received).strip().replace("\N{MINUS SIGN}", "-")
    if config.get("decimal_separator") == ",":
        raw = raw.replace(",", ".")
    required_unit = config.get("required_unit")
    if isinstance(required_unit, str) and required_unit:
        aliases = [required_unit, *(config.get("unit_aliases") or [])]
        matched = next(
            (
                alias for alias in sorted((str(item) for item in aliases), key=len, reverse=True)
                if raw.casefold().endswith(alias.casefold())
            ),
            None,
        )
        if matched is None:
            return 0.0
        raw = raw[: -len(matched)].strip()
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", raw):
        return 0.0
    value = float(raw)
    if not math.isfinite(value):
        return 0.0
    if "value" in config:
        expected = config["value"]
        if isinstance(expected, bool) or not isinstance(expected, (int, float)):
            return None
        difference = abs(value - float(expected))
        checks: list[bool] = []
        if "absolute_tolerance" in config:
            checks.append(difference <= max(0.0, float(config["absolute_tolerance"])))
        if "relative_tolerance" in config:
            checks.append(
                difference <= abs(float(expected)) * max(0.0, float(config["relative_tolerance"]))
            )
        correct = (
            all(checks) if config.get("tolerance_mode") == "both" else any(checks)
        ) if checks else difference == 0
        return 1.0 if correct else 0.0
    if "min" not in config and "max" not in config:
        return None
    above = "min" not in config or (
        value > float(config["min"])
        if config.get("include_min") is False
        else value >= float(config["min"])
    )
    below = "max" not in config or (
        value < float(config["max"])
        if config.get("include_max") is False
        else value <= float(config["max"])
    )
    return 1.0 if above and below else 0.0


def _builtin_evaluation_score(config: dict, received: object) -> float | None:
    mode = config.get("mode", "exact")
    if mode not in BUILTIN_EVALUATION_MODES:
        return None
    expected = config.get("expected")
    if mode == "exact":
        return 1.0 if _texts_match(str(received).strip(), str(expected).strip()) else 0.0
    if mode == "normalized_any" and isinstance(expected, list) and expected:
        candidate = _normalized_text(received, case_sensitive=bool(config.get("case_sensitive")))
        return 1.0 if any(
            _texts_match(
                candidate,
                _normalized_text(answer, case_sensitive=bool(config.get("case_sensitive"))),
            )
            for answer in expected
        ) else 0.0
    if mode == "set" and isinstance(received, list) and isinstance(expected, list):
        return 1.0 if {str(value) for value in received} == {str(value) for value in expected} else 0.0
    if mode == "regions" and isinstance(received, dict) and isinstance(expected, list):
        selected = received.get("regionIds")
        if not isinstance(selected, list):
            return None
        expected_ids = {str(value) for value in expected}
        selected_ids = {str(value) for value in selected}
        if not expected_ids:
            return None
        if selected_ids == expected_ids:
            return 1.0
        return (
            len(expected_ids & selected_ids) / max(len(expected_ids), len(selected_ids))
            if selected_ids
            else 0.0
        )
    if mode == "assignments":
        return _score_assignments(received, expected)
    if mode == "sequence":
        return _score_sequence(received, expected)
    if mode == "keyed_text":
        return _score_keyed_text(
            received,
            expected,
            case_sensitive=bool(config.get("case_sensitive")),
        )
    if mode == "numeric":
        return _score_numeric(received, config)
    return None


class ActivityDefinitionService:
    def __init__(
        self,
        definitions: ActivityDefinitionRepository,
        states: ActivityStateRepository,
        ports: ActivityPortRegistry | None = None,
    ) -> None:
        self.definitions = definitions
        self.states = states
        self.ports = ports or ActivityPortRegistry()

    async def get(self, activity_id: uuid.UUID, org_id: uuid.UUID) -> ActivityDefinition:
        activity = await self.definitions.get_scoped(activity_id, org_id)
        if activity is None:
            raise NotFoundError("activity_definitions", str(activity_id))
        return activity

    def missing_ports(self, activity: ActivityDefinition) -> list[str]:
        return sorted(
            port for port in (activity.required_ports or [])
            if port not in BUILTIN_PORTS and not self.ports.has(port)
        )

    async def create(self, *, org_id: uuid.UUID, body: ActivityDefinitionCreate) -> ActivityDefinition:
        if body.node_id is None:  # defensive; schema currently requires it
            raise ValidationError("node_id is required", field="node_id")
        existing = await self.definitions.get_version(
            org_id=org_id, definition_key=body.definition_key, version=body.version
        )
        values = body.model_dump()
        if existing is not None:
            if all(getattr(existing, key) == value for key, value in values.items()):
                return existing
            raise ConflictError(
                "activity definition versions are immutable; publish a new version",
                field="version",
            )
        return await self.definitions.create(org_id=org_id, **values)

    def ensure_ready(self, activity: ActivityDefinition, operation: str) -> PortDeclined | None:
        if not activity.enabled:
            return PortDeclined("activity_disabled")
        missing = self.missing_ports(activity)
        if missing:
            return PortDeclined("missing_ports:" + ",".join(missing))
        if operation not in (activity.required_ports or []) and operation in {"evaluation", "simulation", "execution"}:
            return PortDeclined(f"operation_not_declared:{operation}")
        return None

    async def evaluate(self, activity: ActivityDefinition, submission: dict) -> dict | PortDeclined:
        decline = self.ensure_ready(activity, "evaluation")
        if decline:
            return decline
        adapter = self.ports.get("evaluation")
        if adapter is not None:
            return await adapter.evaluate(activity.private_definition, submission)  # type: ignore[attr-defined]

        config = (activity.private_definition or {}).get("evaluation")
        if not isinstance(config, dict):
            return self._broken(activity, "missing_evaluation_definition")
        received = submission.get("answer")
        score = _builtin_evaluation_score(config, received)
        if score is None:
            return self._broken(activity, "unsupported_evaluation_mode")
        correct = score == 1.0
        outcome = "correct" if correct else "incorrect" if score == 0.0 else "partial"
        return {
            "outcome": outcome,
            "passed": correct,
            "score": score,
            "feedback": public_feedback(activity.public_definition, outcome),
        }

    @staticmethod
    def _broken(activity: ActivityDefinition, reason: str) -> PortDeclined:
        """Decline, and say so out loud: this is a generation defect, not a learner error.

        Without the log line an activity that can never be graded is invisible — the
        learner sees a dead check, the quality bench sees nothing, and the same broken
        shape is generated again. ``exc_info`` would be noise (there is no exception); the
        coordinates are what a maintainer needs to find the offending definition.
        """
        logger.warning(
            "activity %s (%s) cannot be evaluated: %s",
            activity.id,
            activity.component_id,
            reason,
        )
        return PortDeclined(reason)

    async def transition(self, activity: ActivityDefinition, state: dict, action: str) -> dict | PortDeclined:
        decline = self.ensure_ready(activity, "simulation")
        if decline:
            return decline
        adapter = self.ports.get("simulation")
        if adapter is not None:
            return await adapter.transition(activity.private_definition, state, action)  # type: ignore[attr-defined]
        machine = (activity.private_definition or {}).get("simulation")
        if not isinstance(machine, dict):
            return PortDeclined("missing_simulation_definition")
        current = str(state.get("current") or machine.get("initial") or "")
        transition = (machine.get("transitions") or {}).get(current, {}).get(action)
        if not isinstance(transition, str):
            return PortDeclined("transition_not_available")
        return {**state, "current": transition}

    async def execute(self, activity: ActivityDefinition, submission: dict) -> dict | PortDeclined:
        decline = self.ensure_ready(activity, "execution")
        if decline:
            return decline
        adapter = self.ports.get("execution")
        if adapter is None:
            return PortDeclined("missing_ports:execution")
        return await adapter.execute(activity.private_definition, submission)  # type: ignore[attr-defined]


def public_feedback(public_definition: Mapping[str, Any] | None, outcome: str) -> str | None:
    """The author's reaction line for one outcome, from the half the client already has.

    Kept as a function rather than inlined in :meth:`ActivityDefinitionService.evaluate`
    because the idempotent replay of ``POST /activities/{id}/evaluate`` has to reproduce
    the same line from a stored *outcome* alone. The alternative — storing the sentence
    with the recorded verdict — would put authored course content into ``learning_events``,
    which carries bounded telemetry and nothing else.
    """
    feedback = (public_definition or {}).get("feedback")
    if not isinstance(feedback, Mapping):
        return None
    key = {"correct": "positive", "partial": "partial"}.get(outcome, "negative")
    value = feedback.get(key)
    return value if isinstance(value, str) else None


def validated_score(evaluated: Mapping[str, Any]) -> tuple[str, float, bool, str | None]:
    """Refuse to move a learner's mastery on an evaluation that is not scored evidence.

    An ``evaluation`` port adapter is free to return whatever it likes, so every value
    that reaches ``MasteryEvidenceService`` is checked first. ``hints_used`` is
    deliberately **not** read from here: on the ``/evaluate`` path the record of what was
    actually disclosed to this learner is ``learner_node_states.hints_used``, and a number
    an adapter reports about itself is not that record.

    Twin of ``ExperienceAttemptService._validated_score``, which does the same job for the
    ``/attempts`` path and additionally carries the adapter's hint count. The two should
    collapse into this one the next time that service is touched.
    """
    outcome = evaluated.get("outcome")
    if outcome not in {"correct", "incorrect", "partial"}:
        raise ValidationError("evaluation did not produce scored evidence")
    score_value = evaluated.get("score")
    passed_value = evaluated.get("passed")
    if isinstance(score_value, bool) or not isinstance(score_value, (int, float)):
        raise ValidationError("evaluation returned an invalid score")
    score = float(score_value)
    if not 0.0 <= score <= 1.0 or not isinstance(passed_value, bool):
        raise ValidationError("evaluation returned an invalid scoring shape")
    raw_error = evaluated.get("error_kind")
    if raw_error is not None and not isinstance(raw_error, str):
        raise ValidationError("evaluation returned an invalid error_kind")
    # An adapter may supply a richer, server-owned classification. The neutral bridge must
    # not infer pedagogy from a concrete component id.
    error_kind = raw_error or (None if passed_value else f"{outcome}_response")
    return str(outcome), score, passed_value, error_kind


def operation_payload(value: dict | PortDeclined) -> dict[str, Any]:
    if isinstance(value, PortDeclined):
        return {"status": "declined", "result": None, "decline_reason": value.reason}
    return {"status": "completed", "result": value, "decline_reason": None}
