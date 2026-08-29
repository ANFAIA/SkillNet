"""``courses.navigation_mode`` (free/sequential) on the surfaces that set and read it.

The rule itself — who may open which lesson — lives in
``tests/test_node_progression.py``, and the refusal it produces in
``tests/test_node_completion.py``. What is pinned here is the settings path the dial
rides, which is deliberately the one ``tutor_style`` already rides:

1. ``CourseService.update`` validates a change the way it validates
   ``artifact_generate_policy`` and ``tutor_style`` — a bad value raises
   ``ValidationError`` with the field named, a good one is cast to the enum and
   persisted. Without this the bad value reaches PostgreSQL and comes back a 500 rather
   than the 422 an admin form can put next to the field.
2. the projector in ``routes/courses.py`` reports the **declared** setting, and reports
   ``free`` for a row that predates migration 0034.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.exceptions import ValidationError
from src.models import ArtifactGeneratePolicy, CourseNavigationMode, CourseTutorStyle
from src.routes.courses import _navigation_mode
from src.services.course_service import CourseService


def _repo(**overrides):
    defaults = dict(
        get_scoped=AsyncMock(),
        update=AsyncMock(side_effect=lambda course, **kwargs: course),
    )
    defaults.update(overrides)
    return SimpleNamespace(session=SimpleNamespace(), **defaults)


def _course():
    return SimpleNamespace(
        id=uuid.uuid4(),
        tutor_style=CourseTutorStyle.SOCRATIC,
        navigation_mode=CourseNavigationMode.FREE,
        artifact_generate_policy=ArtifactGeneratePolicy.ADMIN,
    )


# --------------------------------------------------------------------------------------
# 1. PUT /courses/{id} validates it like every other course setting
# --------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_update_rejects_an_invalid_navigation_mode() -> None:
    course = _course()
    repo = _repo(get_scoped=AsyncMock(return_value=course))

    with pytest.raises(ValidationError):
        await CourseService(repo).update(
            course_id=course.id,
            org_id=uuid.uuid4(),
            changes={"navigation_mode": "mastery"},
        )


@pytest.mark.asyncio
async def test_update_accepts_a_valid_navigation_mode() -> None:
    course = _course()
    repo = _repo(get_scoped=AsyncMock(return_value=course))

    updated = await CourseService(repo).update(
        course_id=course.id,
        org_id=uuid.uuid4(),
        changes={"navigation_mode": "sequential"},
    )

    assert updated is course
    repo.update.assert_awaited_once_with(
        course, navigation_mode=CourseNavigationMode.SEQUENTIAL
    )


@pytest.mark.asyncio
async def test_a_course_update_that_says_nothing_about_it_leaves_it_alone() -> None:
    """The body is dumped with ``exclude_unset``, so an untouched dial is absent.

    Worth an assertion because the failure would be silent and one-directional: a ``None``
    leaking through as a value would reset every course somebody renamed back to ``free``.
    """
    course = _course()
    repo = _repo(get_scoped=AsyncMock(return_value=course))

    await CourseService(repo).update(
        course_id=course.id, org_id=uuid.uuid4(), changes={"title": "Otro titulo"}
    )

    repo.update.assert_awaited_once_with(course, title="Otro titulo")


# --------------------------------------------------------------------------------------
# 2. The admin screen can read back what it wrote
# --------------------------------------------------------------------------------------
def test_the_course_projection_carries_the_declared_mode() -> None:
    """The *declared* setting, not the one resolved for the caller.

    ``resolve_navigation`` reports ``free`` to an admin so their own preview is never
    paced — and an admin who saw ``free`` on the course they had just set to
    ``sequential`` would reasonably conclude the save had failed. Two readers, two
    questions; this is the one that answers "what is this course set to".
    """
    assert _navigation_mode(SimpleNamespace(navigation_mode="sequential")) == "sequential"
    assert _navigation_mode(SimpleNamespace(navigation_mode=CourseNavigationMode.FREE)) == "free"


def test_a_course_row_from_before_the_migration_projects_as_free() -> None:
    """``getattr`` with a fallback, like every other projector in that module.

    The hand-built ``Course`` stand-ins the unit tests project have no such attribute, and
    neither would a row read through a stale mapping. ``free`` is the honest answer: it is
    what the course was doing.
    """
    assert _navigation_mode(SimpleNamespace()) == "free"
    assert _navigation_mode(SimpleNamespace(navigation_mode=None)) == "free"
