"""The single decision point for v1-static vs v2-dynamic delivery.

A course is dynamic when it opts in (``delivery_mode='dynamic'``) AND a human has
validated the schema (``schema_status='validated'``). Everything else is static.
"""

from __future__ import annotations

import enum
from typing import Literal, Protocol

from src.models.course import CourseDeliveryMode, CourseSchemaStatus

Delivery = Literal["static", "dynamic"]


class _CourseLike(Protocol):
    delivery_mode: object
    schema_status: object


def _value(raw: object) -> str:
    """Enum member or raw string -> its string value."""
    return raw.value if isinstance(raw, enum.Enum) else str(raw)


def resolve_delivery(course: _CourseLike) -> Delivery:
    """Return the delivery path for a course.

    Dynamic requires the course opted in AND a human-validated schema.
    Anything else stays on the v1 path.
    """
    if _value(course.delivery_mode) != CourseDeliveryMode.DYNAMIC.value:
        return "static"
    if _value(course.schema_status) != CourseSchemaStatus.VALIDATED.value:
        return "static"
    return "dynamic"
