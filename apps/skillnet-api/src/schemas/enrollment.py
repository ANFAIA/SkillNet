"""Enrollment schemas."""

import uuid
from datetime import date, datetime
from typing import Literal

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
    #: Same **effective** value as ``CourseRead.delivery_mode`` (``resolve_delivery``, so
    #: the flag and the schema gate are folded in). It lives here as well as on the course
    #: because an employee cannot call ``GET /courses`` at all — that route is admin-only —
    #: so their own two lists ("Mis cursos", the dashboard) have no other way to tell a
    #: node-based course from a v1 one before opening it. ``static`` whenever the course
    #: is not loaded, which is the same value the flag-off deployment produces.
    delivery_mode: Literal["static", "dynamic"] = "static"


class EnrollmentCreate(BaseModel):
    user_ids: list[uuid.UUID]
    course_id: uuid.UUID
    deadline: date | None = None
