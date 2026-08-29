"""Course schemas: summary, nested detail, and create/update bodies."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.schemas.exercise import ExerciseRead


class LessonRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    content: str
    position: int
    exercises: list[ExerciseRead] = []


class ModuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    summary: str | None = None
    position: int
    lessons: list[LessonRead] = []


class CourseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None = None
    outcome: str | None = None
    status: str
    source_document_id: uuid.UUID | None = None
    folder_id: uuid.UUID | None = None
    folder_name: str | None = None
    created_at: datetime
    updated_at: datetime
    module_count: int | None = None
    node_count: int | None = None
    schema_status: str | None = None
    #: Marks the per-org demo course. Read-only, set by the demo seed; the admin preview
    #: screen uses it to decide whether to offer the personalization variant toggle.
    is_demo: bool = False
    #: The **effective** delivery path of §11.3, not the raw ``courses.delivery_mode``
    #: column. It is whatever ``resolve_delivery`` computes, which checks the column and
    #: the schema status — so with the schema not yet validated every course reads
    #: ``static`` here and no v1 screen can start advertising a surface that would 404.
    #:
    #: Defaults to ``static`` so the safe value is the one you get by forgetting to pass
    #: it. Every route in ``src/routes/courses.py`` fills it in from ``resolve_delivery``.
    delivery_mode: Literal["static", "dynamic"] = "static"
    artifact_generate_policy: Literal["admin", "everyone", "selected"] = "admin"
    artifact_generator_ids: list[uuid.UUID] = []
    can_generate_artifacts: bool = False
    #: How the learner tutor answers inside this course. Auto-detected at
    #: creation by the schema designer, editable via ``PUT /courses/{id}``.
    tutor_style: Literal["socratic", "direct"] = "socratic"
    #: In what order this course's lessons may be opened. ``free`` is what every course
    #: did before the column existed — the whole list open, walked in any order — so it
    #: is both the default and the value you get by forgetting to pass it. ``sequential``
    #: opens a lesson once the previous one is finished; the per-node answer is
    #: ``NodeSummaryRead.available``, which is what a client should actually render.
    navigation_mode: Literal["free", "sequential"] = "free"
    #: What this course does with the images embedded in its source document.
    #: ``auto`` is the rule (diagrams get rebuilt, screenshots get kept); the two
    #: overrides are policy escapes. Never asked at creation, edited afterwards.
    image_source_policy: Literal["auto", "keep_original", "rebuild"] = "auto"
    #: Whether a creation run owns this course and how the last one ended (migration
    #: 0025). ``idle`` for anything nobody is creating, which is every course made
    #: before the column existed — so the safe value is the one you get by default.
    generation_state: Literal["idle", "in_progress", "failed", "complete"] = "idle"
    #: Short, safe reason a creation run failed. Never a raw exception.
    generation_error: str | None = None
    generation_failed_at: datetime | None = None


class CourseDetail(CourseRead):
    modules: list[ModuleRead] = []


class CourseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    outcome: str | None = None
    source_document_id: uuid.UUID | None = None
    document_ids: list[uuid.UUID] | None = None
    folder_id: uuid.UUID | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class CourseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    outcome: str | None = None
    folder_id: uuid.UUID | None = None
    artifact_generate_policy: Literal["admin", "everyone", "selected"] | None = None
    artifact_generator_ids: list[uuid.UUID] | None = None
    tutor_style: Literal["socratic", "direct"] | None = None
    navigation_mode: Literal["free", "sequential"] | None = None
    image_source_policy: Literal["auto", "keep_original", "rebuild"] | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class LessonUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
