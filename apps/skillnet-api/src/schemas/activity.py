"""Explicit public contracts for server-owned rich activities."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.models.activity_definition import ActivityDefinition, ActivityFamily, ActivityState
from src.services.activity_ports import PORT_NAMES

_PRIVATE_KEYS = frozenset({
    "answer", "answers", "answerkey", "acceptedanswer", "acceptedanswers",
    "correct", "correctanswer", "correctanswers", "correctcategories",
    "correctmatches", "correctoptionids", "correctorder", "correctvalue",
    "evaluation", "evaluationconfig", "expected", "expectedanswer",
    "expectedanswers", "grading", "privatedefinition", "private_definition",
    "rubric", "rule", "solution", "solutions", "tolerance",
})


def _normalized_private_key(key: object) -> str:
    return "".join(character for character in str(key).lower() if character.isalnum() or character == "_")


def assert_public_payload(value: Any, path: str = "public_definition") -> None:
    """Fail closed when a public tree contains a server-owned assessment key."""
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = _normalized_private_key(key)
            compact = normalized.replace("_", "")
            if normalized in _PRIVATE_KEYS or compact in _PRIVATE_KEYS or compact.startswith("answerkey"):
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
    #: ``true`` once this learner has been shown the worked solution — asked for, or handed
    #: over at the fourth failure. Server-owned, from ``learner_activity_states``, next to
    #: the client-owned ``state`` blob rather than inside it, because the client must not be
    #: able to un-reveal a solution by writing its own state back.
    #:
    #: Without it the closure lived only in component memory: a reload showed the activity
    #: open again, ready to be answered by somebody who had already read the answer.
    solution_revealed: bool = False

    @classmethod
    def of(
        cls,
        activity_id: uuid.UUID,
        row: ActivityState | None,
        *,
        solution_revealed: bool = False,
    ) -> "ActivityStateRead":
        return cls(
            activity_id=activity_id,
            state=dict(row.state or {}) if row else {},
            solution_revealed=solution_revealed,
        )


class ActivitySubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    submission: dict = Field(default_factory=dict)
    #: Client-minted idempotency key for ``POST /activities/{id}/evaluate``.
    #:
    #: Optional, and additive on purpose: the model forbids extra fields, so a client that
    #: does not send it keeps working unchanged. When it *is* sent, a repeat of the same
    #: submission replays the first verdict instead of grading again — which matters now
    #: that grading an ``assessment`` moves mastery, and a double click would otherwise
    #: count two failures. Reusing one id for a **different** submission is a ``409``,
    #: exactly as on ``POST /activities/{id}/attempts``.
    attempt_id: uuid.UUID | None = None


class ActivityAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(min_length=1, max_length=160)
    state: dict = Field(default_factory=dict)


class ActivityOperationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["completed", "declined"]
    result: dict | None = None
    decline_reason: str | None = None


class ActivitySolutionRead(BaseModel):
    """The worked solution of one activity, written out for a learner who asked for it.

    Deliberately the same two fields ``activity_solution.render_solution`` already puts
    inside ``result.solution`` on ``POST /activities/{id}/evaluate``, and not a shape of
    its own: the answer arrives by two roads — handed over by rule 8, or requested — and a
    client that had to tell them apart would be reading the same fact in two vocabularies.

    ``POST /activities/{id}/solution`` answers ``null`` instead of this model when the
    evaluation mode cannot be rendered honestly. That is an answer, not an error: the
    learner asked, there is nothing to print, and they still have to be let through.
    """

    model_config = ConfigDict(extra="forbid")

    solution: str
    explanation: str | None = None


class ActivityProgressRead(BaseModel):
    """Server-owned ProgressPort snapshot. The client cannot write these fields."""

    model_config = ConfigDict(extra="forbid")

    component_id: str
    status: Literal["not_started", "in_progress", "completed"]
    progress: int
    level: Literal["beginner", "intermediate", "advanced"]


class ActivityAssetRead(BaseModel):
    """Public AssetPort result. Storage paths and hashes never cross this boundary."""

    model_config = ConfigDict(extra="forbid")

    ref: str
    url: str
    mime_type: str
    alt: str
    long_description: str | None = None
    width: int | None = None
    height: int | None = None
    duration_ms: int | None = None
    transcript: list[dict] | None = None
    captions: list[dict] | None = None


DidactEventType = Literal[
    "started",
    "attempted",
    "answered",
    "feedback_viewed",
    "completed",
]


class DidactEventPayload(BaseModel):
    """Bounded telemetry only: never an answer, solution, rubric, or free text."""

    model_config = ConfigDict(extra="forbid")

    attempt_id: uuid.UUID | None = None
    outcome: Literal["correct", "incorrect", "partial", "unscored"] | None = None
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    duration_ms: int | None = Field(default=None, ge=0, le=86_400_000)


class DidactEventEnvelope(BaseModel):
    """Closed, versioned EventPort wire contract."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    event_id: uuid.UUID
    activity_id: uuid.UUID
    component_id: str = Field(min_length=1, max_length=160, pattern=r"^didact\.")
    type: DidactEventType
    occurred_at: datetime
    payload: DidactEventPayload = Field(default_factory=DidactEventPayload)
