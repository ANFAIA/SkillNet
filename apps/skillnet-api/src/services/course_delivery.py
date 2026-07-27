"""The single decision point for v1-static vs v2-dynamic delivery.

Reading ``settings.DYNAMIC_COURSES_MODE`` anywhere other than a route guard
(``src.deps.features``) and this function is forbidden: one flag consulted in ten
places is ten different flags.
"""

from __future__ import annotations

import enum
from typing import Literal, Protocol

from src.models.course import CourseDeliveryMode, CourseSchemaStatus

Delivery = Literal["static", "dynamic"]


class _HasDynamicCoursesMode(Protocol):
    """Just enough of ``Settings`` to decide, so tests need no full Settings object."""

    DYNAMIC_COURSES_MODE: str


class _CourseLike(Protocol):
    delivery_mode: object
    schema_status: object


def _value(raw: object) -> str:
    """Enum member or raw string -> its string value."""
    return raw.value if isinstance(raw, enum.Enum) else str(raw)


def resolve_delivery(
    course: _CourseLike, settings: _HasDynamicCoursesMode
) -> Delivery:
    """Return the delivery path for ``course``.

    Dynamic requires all three: the flag fully ``on``, the course opted in, and a
    human-validated schema. Anything else stays on the untouched v1 path.
    """
    if settings.DYNAMIC_COURSES_MODE != "on":
        return "static"
    if _value(course.delivery_mode) != CourseDeliveryMode.DYNAMIC.value:
        return "static"
    if _value(course.schema_status) != CourseSchemaStatus.VALIDATED.value:
        return "static"
    return "dynamic"
