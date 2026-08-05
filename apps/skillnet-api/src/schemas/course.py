"""Course schemas: summary, nested detail, and create/update bodies."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

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
    created_at: datetime
    module_count: int | None = None
    #: The **effective** delivery path of §11.3, not the raw ``courses.delivery_mode``
    #: column. It is whatever ``resolve_delivery`` computes, which checks the column and
    #: the schema status — so with the schema not yet validated every course reads
    #: ``static`` here and no v1 screen can start advertising a surface that would 404.
    #:
    #: Defaults to ``static`` so the safe value is the one you get by forgetting to pass
    #: it. Every route in ``src/routes/courses.py`` fills it in from ``resolve_delivery``.
    delivery_mode: Literal["static", "dynamic"] = "static"


class CourseDetail(CourseRead):
    modules: list[ModuleRead] = []


class CourseCreate(BaseModel):
    title: str
    description: str | None = None
    outcome: str | None = None
    source_document_id: uuid.UUID | None = None
    document_ids: list[uuid.UUID] | None = None


class CourseUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    outcome: str | None = None


class LessonUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
