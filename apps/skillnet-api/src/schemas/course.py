"""Course schemas: summary, nested detail, and create/update bodies."""

import uuid
from datetime import datetime

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
