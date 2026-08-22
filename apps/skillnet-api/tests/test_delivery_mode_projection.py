"""``delivery_mode`` on the v1 read schemas: promised by §11.3.

Without this field the frontend had no way to tell a node-based course from a v1 one
except by *trying* ``GET /courses/{id}/nodes`` and reading the 404 — which works for the
one screen that already does it and works for nothing else. An admin listing content, or
an employee looking at "Mis cursos", could not label a single row.

The property that makes it safe is the one asserted here: the value is
**``resolve_delivery``**, not ``courses.delivery_mode``. A course opted into ``dynamic``
whose schema is still in draft reads ``static``, because that is the path it is actually
served on. A badge saying "dinamico" over it would send the creator hunting for a node
map that does not exist.

Projection functions only: they are where the value is computed, they take plain objects,
and testing them needs neither a database nor a session. ``tests/test_delivery_resolution.py``
already owns the full truth table of the decision itself.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pytest

from src.models.course import ContentStatus, CourseDeliveryMode, CourseSchemaStatus
from src.models.user import UserRole
from src.routes.courses import _detail, _summary
from src.routes.enrollments import _read

NOW = datetime(2026, 7, 25, 9, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class FakeUser:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    role: UserRole = UserRole.ADMIN


USER = FakeUser()


@dataclass
class FakeCourse:
    delivery_mode: CourseDeliveryMode = CourseDeliveryMode.DYNAMIC
    schema_status: CourseSchemaStatus = CourseSchemaStatus.VALIDATED
    folder_id: uuid.UUID | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    title: str = "Politica de devoluciones"
    description: str | None = None
    outcome: str | None = None
    status: ContentStatus = ContentStatus.PUBLISHED
    source_document_id: uuid.UUID | None = None
    created_at: datetime = NOW
    updated_at: datetime = NOW
    modules: list = field(default_factory=list)
    is_demo: bool = False


@dataclass
class FakeEnrollment:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    course_id: uuid.UUID = field(default_factory=uuid.uuid4)
    user_id: uuid.UUID = field(default_factory=uuid.uuid4)
    status: Any = None
    deadline: Any = None
    score: float | None = None
    started_at: Any = None
    completed_at: Any = None
    course: FakeCourse | None = None

    def __post_init__(self) -> None:
        if self.status is None:
            self.status = _Status()


class _Status:
    """``enrollments.status`` is an enum in the model; the route reads ``.value``."""

    value = "in_progress"


#: (course delivery_mode, schema_status) -> what every read schema must print.
CASES = (
    (CourseDeliveryMode.DYNAMIC, CourseSchemaStatus.VALIDATED, "dynamic"),
    (CourseDeliveryMode.DYNAMIC, CourseSchemaStatus.DRAFT, "static"),
    (CourseDeliveryMode.STATIC, CourseSchemaStatus.VALIDATED, "static"),
)


@pytest.mark.parametrize(("delivery", "schema_status", "expected"), CASES)
def test_course_read_reports_the_effective_delivery_path(
    delivery: CourseDeliveryMode,
    schema_status: CourseSchemaStatus,
    expected: str,
) -> None:
    course = FakeCourse(delivery_mode=delivery, schema_status=schema_status)
    assert _summary(course, 3, user=USER).delivery_mode == expected


@pytest.mark.parametrize(("delivery", "schema_status", "expected"), CASES)
def test_course_detail_agrees_with_the_summary(
    delivery: CourseDeliveryMode,
    schema_status: CourseSchemaStatus,
    expected: str,
) -> None:
    """Two projections of the same course disagreeing would make the badge flicker
    between the list and the detail screen."""
    course = FakeCourse(delivery_mode=delivery, schema_status=schema_status)
    assert _detail(course, strip=True, user=USER).delivery_mode == expected


@pytest.mark.parametrize(("delivery", "schema_status", "expected"), CASES)
def test_enrollment_read_carries_the_same_value(
    delivery: CourseDeliveryMode,
    schema_status: CourseSchemaStatus,
    expected: str,
) -> None:
    """An employee cannot call ``GET /courses`` — it is admin-only — so their own lists
    read the mode off the enrollment or not at all."""
    course = FakeCourse(delivery_mode=delivery, schema_status=schema_status)
    enrollment = FakeEnrollment(course=course)
    assert _read(enrollment, 0.5).delivery_mode == expected


def test_an_enrollment_with_no_course_loaded_reads_static() -> None:
    """Absence of information is never a reason to advertise a surface."""
    assert _read(FakeEnrollment(course=None), None).delivery_mode == "static"
