"""Business rules shared by all declarative Didact activity families."""

from __future__ import annotations

import hmac
import math
import re
import uuid
from typing import Any

from src.core.exceptions import ConflictError, NotFoundError, ValidationError
from src.models.activity_definition import ActivityDefinition
from src.repositories.activity_definition_repo import (
    ActivityDefinitionRepository,
    ActivityStateRepository,
)
from src.schemas.activity import ActivityDefinitionCreate
from src.services.activity_ports import ActivityPortRegistry, PortDeclined

BUILTIN_PORTS = frozenset({"assets", "evaluation", "persistence", "progress", "simulation"})


def _normalized_text(value: object, *, case_sensitive: bool = False) -> str:
    normalized = " ".join(str(value).strip().split())
    return normalized if case_sensitive else normalized.casefold()


def _score_assignments(received: object, expected: object) -> float | None:
    if not isinstance(received, dict) or not isinstance(expected, dict) or not expected:
        return None
    return sum(
        hmac.compare_digest(str(received.get(key, "")), str(answer))
        for key, answer in expected.items()
    ) / len(expected)


def _score_sequence(received: object, expected: object) -> float | None:
    if not isinstance(received, list) or not isinstance(expected, list) or not expected:
        return None
    if len(received) != len(expected):
        return 0.0
    return sum(
        hmac.compare_digest(str(actual), str(answer))
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
            hmac.compare_digest(
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
    expected = config.get("expected")
    if mode == "exact":
        return 1.0 if hmac.compare_digest(str(received).strip(), str(expected).strip()) else 0.0
    if mode == "normalized_any" and isinstance(expected, list) and expected:
        candidate = _normalized_text(received, case_sensitive=bool(config.get("case_sensitive")))
        return 1.0 if any(
            hmac.compare_digest(
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
            return PortDeclined("missing_evaluation_definition")
        received = submission.get("answer")
        score = _builtin_evaluation_score(config, received)
        if score is None:
            return PortDeclined("unsupported_evaluation_mode")
        correct = score == 1.0
        outcome = "correct" if correct else "incorrect" if score == 0.0 else "partial"
        feedback = (activity.public_definition or {}).get("feedback", {})
        public_feedback = (
            feedback.get("positive" if correct else "partial" if outcome == "partial" else "negative")
            if isinstance(feedback, dict)
            else None
        )
        return {
            "outcome": outcome,
            "passed": correct,
            "score": score,
            "feedback": public_feedback,
        }

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


def operation_payload(value: dict | PortDeclined) -> dict[str, Any]:
    if isinstance(value, PortDeclined):
        return {"status": "declined", "result": None, "decline_reason": value.reason}
    return {"status": "completed", "result": value, "decline_reason": None}
