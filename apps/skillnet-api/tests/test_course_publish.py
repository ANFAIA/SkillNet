"""Publish rules: v1 still needs a lesson; v2 needs a validated schema and a node."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.exceptions import ValidationError
from src.models import ContentStatus
from src.services.course_service import CourseService


def _repo(**overrides):
    defaults = dict(
        get_detail=AsyncMock(),
        count_active_nodes=AsyncMock(return_value=0),
        update=AsyncMock(side_effect=lambda course, **kwargs: course),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_publish_accepts_a_validated_dynamic_course_without_lessons() -> None:
    course = SimpleNamespace(
        id=uuid.uuid4(),
        title="Taquilla",
        outcome="Vender una entrada de prueba",
        modules=[],
        delivery_mode="dynamic",
        schema_status="validated",
        status=ContentStatus.DRAFT,
    )
    repo = _repo(
        get_detail=AsyncMock(return_value=course),
        count_active_nodes=AsyncMock(return_value=4),
    )

    published = await CourseService(repo).publish(
        course_id=course.id, org_id=uuid.uuid4()
    )

    assert published is course
    repo.update.assert_awaited_once_with(course, status=ContentStatus.PUBLISHED)


@pytest.mark.asyncio
async def test_publish_rejects_a_dynamic_course_with_no_nodes() -> None:
    course = SimpleNamespace(
        id=uuid.uuid4(),
        title="Taquilla",
        outcome="Vender una entrada de prueba",
        modules=[],
        delivery_mode="dynamic",
        schema_status="validated",
    )
    repo = _repo(
        get_detail=AsyncMock(return_value=course),
        count_active_nodes=AsyncMock(return_value=0),
    )

    with pytest.raises(ValidationError, match="at least one node"):
        await CourseService(repo).publish(course_id=course.id, org_id=uuid.uuid4())
    repo.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_still_requires_a_lesson_on_the_static_path() -> None:
    course = SimpleNamespace(
        id=uuid.uuid4(),
        title="Alergenos",
        outcome="Informar sin equivocarse",
        modules=[],
        delivery_mode="static",
        schema_status="draft",
    )
    repo = _repo(get_detail=AsyncMock(return_value=course))

    with pytest.raises(ValidationError, match="at least one module"):
        await CourseService(repo).publish(course_id=course.id, org_id=uuid.uuid4())
    repo.count_active_nodes.assert_not_awaited()
    repo.update.assert_not_awaited()
