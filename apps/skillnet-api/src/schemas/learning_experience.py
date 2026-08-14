"""Closed contracts for provider-neutral learning experiences and evidence."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AliasChoices,
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

Outcome = Literal["correct", "incorrect", "partial", "unscored"]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def _non_empty_unique(values: list[str]) -> list[str]:
    cleaned = [value.strip() for value in values]
    if any(not value for value in cleaned):
        raise ValueError("entries must be non-empty")
    if len(cleaned) != len(set(cleaned)):
        raise ValueError("entries must be unique")
    return cleaned


StringList = Annotated[list[str], AfterValidator(_non_empty_unique)]


class ImmutableContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True, populate_by_name=True)


class ExperienceIntentCreate(ImmutableContract):
    course_id: uuid.UUID
    node_id: uuid.UUID
    intent_key: str = Field(min_length=1, max_length=200)
    version: int = Field(default=1, ge=1)
    objective_id: str = Field(min_length=1, max_length=200)
    objective_version: int = Field(ge=1)
    intent: str = Field(min_length=1, max_length=100)
    learner_actions: StringList = Field(default_factory=list)
    representations: StringList = Field(default_factory=list)
    required_evidence: StringList = Field(default_factory=list)
    feedback_policy: str = Field(min_length=1, max_length=100)
    constraints: dict = Field(default_factory=dict)
    provenance: dict = Field(default_factory=dict)
    contract_digest: Digest


class ExperienceIntentRead(ExperienceIntentCreate):
    intent_id: uuid.UUID = Field(validation_alias="id")
    org_id: uuid.UUID
    created_at: datetime


class ExperienceVariantCreate(ImmutableContract):
    intent_id: uuid.UUID
    variant_key: str = Field(min_length=1, max_length=200)
    version: int = Field(default=1, ge=1)
    representations: StringList = Field(default_factory=list)
    learner_actions: StringList = Field(default_factory=list)
    best_for: StringList = Field(default_factory=list)
    required_capabilities: dict = Field(default_factory=dict)
    selection_policy: dict = Field(default_factory=dict)
    variant_digest: Digest


class ExperienceVariantRead(ExperienceVariantCreate):
    variant_id: uuid.UUID = Field(validation_alias="id")
    org_id: uuid.UUID
    created_at: datetime


class ImplementationBindingCreate(ImmutableContract):
    variant_id: uuid.UUID
    binding_key: str = Field(min_length=1, max_length=200)
    version: int = Field(default=1, ge=1)
    provider: str = Field(min_length=1, max_length=100)
    implementation_id: str = Field(min_length=1, max_length=200)
    implementation_version: int = Field(ge=1)
    definition_ref: str = Field(min_length=1, max_length=240)
    activity_definition_id: uuid.UUID | None = None
    definition_digest: Digest
    assets_digest: Digest | None = None
    catalog_version: str = Field(min_length=1, max_length=100)
    evidence_adapter_version: str | None = Field(default=None, min_length=1, max_length=100)
    renderer_version: str = Field(min_length=1, max_length=100)
    required_ports: StringList = Field(default_factory=list)
    is_fallback: bool = False

    @field_validator("provider", "implementation_id")
    @classmethod
    def normalized_identifier(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("identifier must be non-empty")
        return normalized


class ImplementationBindingRead(ImplementationBindingCreate):
    binding_id: uuid.UUID = Field(validation_alias="id")
    org_id: uuid.UUID
    created_at: datetime


class NormalizedEvidenceCreate(ImmutableContract):
    evidence_key: str = Field(min_length=1, max_length=200)
    objective_id: str = Field(min_length=1, max_length=200)
    objective_version: int = Field(ge=1)
    evidence_type: str = Field(min_length=1, max_length=160)
    outcome: Outcome
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    error_kind: str | None = Field(default=None, min_length=1, max_length=160)
    hints_used: int = Field(default=0, ge=0)
    duration_ms: int | None = Field(default=None, ge=0, le=86_400_000)
    implementation_ref: str = Field(min_length=1, max_length=240)
    evidence_digest: Digest

    @field_validator("score")
    @classmethod
    def unscored_has_no_score(cls, value: float | None, info):
        if info.data.get("outcome") == "unscored" and value is not None:
            raise ValueError("unscored evidence cannot carry a score")
        return value


class NormalizedEvidenceRead(NormalizedEvidenceCreate):
    evidence_id: uuid.UUID = Field(validation_alias="id")
    attempt_id: uuid.UUID
    created_at: datetime


class ExperienceAttemptSubmission(ImmutableContract):
    """Client-owned fields for one idempotent, server-scored attempt."""

    attempt_id: uuid.UUID
    binding_id: uuid.UUID
    submission: dict = Field(default_factory=dict)
    duration_ms: int | None = Field(default=None, ge=0, le=86_400_000)


class ExperienceAttemptCreate(ImmutableContract):
    """Internal command after server-side evaluation, not a client scoring contract."""

    attempt_id: uuid.UUID
    course_id: uuid.UUID
    node_id: uuid.UUID
    intent_id: uuid.UUID
    variant_id: uuid.UUID
    binding_id: uuid.UUID
    activity_definition_id: uuid.UUID | None = None
    request_digest: Digest
    outcome: Outcome
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    passed: bool | None = None
    hints_used: int = Field(default=0, ge=0)
    duration_ms: int | None = Field(default=None, ge=0, le=86_400_000)
    result: dict = Field(default_factory=dict)
    evidence: list[NormalizedEvidenceCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_scoring_shape(self) -> "ExperienceAttemptCreate":
        if self.outcome == "unscored":
            if self.score is not None or self.passed is not None:
                raise ValueError("unscored attempt cannot carry score or passed")
        elif self.score is None or self.passed is None:
            raise ValueError("scored attempt requires score and passed")
        return self


class ExperienceAttemptRead(ExperienceAttemptCreate):
    attempt_id: uuid.UUID = Field(validation_alias=AliasChoices("attempt_id", "id"))
    org_id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    evidence: list[NormalizedEvidenceRead] = Field(default_factory=list)
