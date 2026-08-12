"""Explicit public contracts for server-owned rich activities."""

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.models.activity_definition import ActivityDefinition, ActivityFamily, ActivityState
from src.services.activity_ports import PORT_NAMES

_PRIVATE_KEYS = frozenset({
    "answer", "answers", "answer_key", "correct", "correct_answer", "correct_order",
    "solution", "solutions", "rubric", "evaluation_config", "private_definition",
})


def assert_public_payload(value: Any, path: str = "public_definition") -> None:
    """Fail closed when a public tree contains a server-owned assessment key."""
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in _PRIVATE_KEYS or normalized.startswith("answer_key"):
                raise ValueError(f"{path}.{key} is server-owned")
            assert_public_payload(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_public_payload(child, f"{path}[{index}]")


class ActivityDefinitionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: uuid.UUID
    node_id: uuid.UUID
    source_render_id: uuid.UUID | None = None
    source_knowledge_pack_id: uuid.UUID | None = None
    definition_key: str = Field(min_length=1, max_length=160)
    component_id: str = Field(min_length=1, max_length=160)
    family: ActivityFamily
    version: int = Field(default=1, ge=1)
    public_definition: dict = Field(default_factory=dict)
    private_definition: dict = Field(default_factory=dict)
    required_ports: list[str] = Field(default_factory=list)
    provenance: dict = Field(default_factory=dict)

    @field_validator("public_definition")
    @classmethod
    def no_private_material(cls, value: dict) -> dict:
        assert_public_payload(value)
        return value

    @field_validator("required_ports")
    @classmethod
    def known_ports(cls, value: list[str]) -> list[str]:
        unknown = set(value) - PORT_NAMES
        if unknown:
            raise ValueError(f"unknown ports: {sorted(unknown)}")
        return sorted(set(value))


class ActivityDefinitionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity_id: uuid.UUID
    component_id: str
    family: ActivityFamily
    schema_version: int
    public_definition: dict
    required_ports: list[str]
    provenance: dict
    status: Literal["ready", "declined"]
    decline_reason: str | None

    @classmethod
    def of(cls, activity: ActivityDefinition, *, missing_ports: list[str]) -> "ActivityDefinitionRead":
        declined = not activity.enabled or bool(missing_ports)
        reason = None
        if not activity.enabled:
            reason = "activity_disabled"
        elif missing_ports:
            reason = "missing_ports:" + ",".join(missing_ports)
        return cls(
            activity_id=activity.id,
            component_id=activity.component_id,
            family=activity.family,
            schema_version=activity.version,
            public_definition=dict(activity.public_definition or {}),
            required_ports=list(activity.required_ports or []),
            provenance=dict(activity.provenance or {}),
            status="declined" if declined else "ready",
            decline_reason=reason,
        )


class ActivityStateWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: dict = Field(default_factory=dict)


class ActivityStateRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activity_id: uuid.UUID
    state: dict

    @classmethod
    def of(cls, activity_id: uuid.UUID, row: ActivityState | None) -> "ActivityStateRead":
        return cls(activity_id=activity_id, state=dict(row.state or {}) if row else {})


class ActivitySubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    submission: dict = Field(default_factory=dict)


class ActivityAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(min_length=1, max_length=160)
    state: dict = Field(default_factory=dict)


class ActivityOperationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["completed", "declined"]
    result: dict | None = None
    decline_reason: str | None = None
