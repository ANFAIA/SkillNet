"""Enrollment schemas."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class EnrollmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    course_id: uuid.UUID
    user_id: uuid.UUID
    status: str
    deadline: date | None = None
    score: float | None = None
    progress: float | None = None
    course_title: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class EnrollmentCreate(BaseModel):
    user_ids: list[uuid.UUID]
    course_id: uuid.UUID
    deadline: date | None = None
