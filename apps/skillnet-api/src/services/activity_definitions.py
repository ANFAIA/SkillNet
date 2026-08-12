"""Business rules shared by all declarative Didact activity families."""

from __future__ import annotations

import hmac
import uuid
from typing import Any

from src.core.exceptions import NotFoundError, ValidationError
from src.models.activity_definition import ActivityDefinition
from src.repositories.activity_definition_repo import (
    ActivityDefinitionRepository,
    ActivityStateRepository,
)
from src.schemas.activity import ActivityDefinitionCreate
from src.services.activity_ports import ActivityPortRegistry, PortDeclined

BUILTIN_PORTS = frozenset({"evaluation", "persistence", "simulation"})


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
            return await self.definitions.update(existing, **values)
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
        expected = config.get("expected")
        received = submission.get("answer")
        mode = config.get("mode", "exact")
        if mode == "exact":
            correct = hmac.compare_digest(str(received).strip(), str(expected).strip())
        elif mode == "set" and isinstance(received, list) and isinstance(expected, list):
            correct = {str(v) for v in received} == {str(v) for v in expected}
        else:
            return PortDeclined("unsupported_evaluation_mode")
        feedback = (activity.public_definition or {}).get("feedback", {})
        public_feedback = (
            feedback.get("positive" if correct else "negative")
            if isinstance(feedback, dict)
            else None
        )
        return {
            "outcome": "correct" if correct else "incorrect",
            "passed": correct,
            "score": 1.0 if correct else 0.0,
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
