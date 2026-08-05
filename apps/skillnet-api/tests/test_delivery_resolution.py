"""Truth table for ``resolve_delivery``: 2 delivery_mode x 2 schema_status.

No DB, no network: ``resolve_delivery`` takes plain objects on purpose.
"""

from dataclasses import dataclass

import pytest

from src.models.course import CourseDeliveryMode, CourseSchemaStatus
from src.services.course_delivery import resolve_delivery


@dataclass
class FakeCourse:
    delivery_mode: CourseDeliveryMode
    schema_status: CourseSchemaStatus


DELIVERY_MODES = (CourseDeliveryMode.STATIC, CourseDeliveryMode.DYNAMIC)
SCHEMA_STATUSES = (CourseSchemaStatus.PROPOSED, CourseSchemaStatus.VALIDATED)

# The one and only combination that yields "dynamic".
TRUTH_TABLE = [
    (
        delivery,
        status,
        "dynamic"
        if (
            delivery is CourseDeliveryMode.DYNAMIC
            and status is CourseSchemaStatus.VALIDATED
        )
        else "static",
    )
    for delivery in DELIVERY_MODES
    for status in SCHEMA_STATUSES
]


def test_truth_table_has_four_cases():
    assert len(TRUTH_TABLE) == 4
    assert sum(1 for *_, expected in TRUTH_TABLE if expected == "dynamic") == 1


@pytest.mark.parametrize(("delivery", "status", "expected"), TRUTH_TABLE)
def test_resolve_delivery(delivery, status, expected):
    course = FakeCourse(delivery_mode=delivery, schema_status=status)
    assert resolve_delivery(course) == expected


@pytest.mark.parametrize("status", list(CourseSchemaStatus))
def test_only_validated_can_be_dynamic(status):
    course = FakeCourse(delivery_mode=CourseDeliveryMode.DYNAMIC, schema_status=status)
    result = resolve_delivery(course)
    assert result == ("dynamic" if status is CourseSchemaStatus.VALIDATED else "static")


def test_accepts_raw_string_values():
    """Rows loaded via raw SQL hand back strings, not enum members."""
    course = FakeCourse(delivery_mode="dynamic", schema_status="validated")
    assert resolve_delivery(course) == "dynamic"
