"""Request/response schemas for the admin course-schema surface (§11.1).

``CourseSchemaUpdate`` is a **full replacement**, not a partial PATCH: order and the
prerequisite graph have to be validated as a whole, and a partial patch cannot say
"this node is gone".
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.models import NodeCriticality, UiFormat

Criticality = Literal["critical", "recommended", "contextual"]
UiFormatName = Literal["explanation", "simulation", "exercise", "chart", "mixed"]


class SchemaProposeRequest(BaseModel):
    source_document_id: uuid.UUID | None = None
    intent_density: int = Field(default=3, ge=1, le=5)


class SchemaProposeResponse(BaseModel):
    job_id: str


class CourseNodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    summary: str
    outcome: str | None = None
    criticality: Criticality
    position: int
    mastery_threshold: float
    estimated_minutes: int | None = None
    default_ui_format: UiFormatName
    skill_id: uuid.UUID | None = None
    seed_lesson_id: uuid.UUID | None = None
    source_document_id: uuid.UUID | None = None
    source_headings: list[str] = []
    prerequisite_node_ids: list[uuid.UUID] = []
    reviewed_at: datetime | None = None
    reviewed_by: uuid.UUID | None = None
    archived: bool = False


class CourseSchemaRead(BaseModel):
    course_id: uuid.UUID
    schema_status: str
    schema_version: int
    delivery_mode: str
    intent_density: int
    validated_by: uuid.UUID | None = None
    validated_at: datetime | None = None
    warnings: list[str] = []
    nodes: list[CourseNodeRead] = []


class CourseNodeInput(BaseModel):
    """One node of a replacement schema. ``id`` absent means "create this node".

    ``prerequisite_node_ids`` holds real uuids, so a node created by this very
    request cannot yet be anybody's prerequisite; unknown ids are dropped with a
    warning rather than silently accepted.
    """

    id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1)
    outcome: str | None = None
    criticality: Criticality = NodeCriticality.RECOMMENDED.value
    position: int | None = Field(default=None, ge=1)
    mastery_threshold: float | None = Field(default=None, gt=0, le=1)
    estimated_minutes: int | None = Field(default=None, ge=1, le=240)
    default_ui_format: UiFormatName = UiFormat.EXPLANATION.value
    skill_id: uuid.UUID | None = None
    seed_lesson_id: uuid.UUID | None = None
    source_document_id: uuid.UUID | None = None
    source_headings: list[str] = []
    prerequisite_node_ids: list[uuid.UUID] = []
    archived: bool | None = None

    @field_validator("title", "summary")
    @classmethod
    def _strip(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class CourseSchemaUpdate(BaseModel):
    intent_density: int | None = Field(default=None, ge=1, le=5)
    nodes: list[CourseNodeInput]


class NodeReviewResponse(BaseModel):
    node_id: uuid.UUID
    reviewed_at: datetime | None = None
    reviewed_by: uuid.UUID | None = None
