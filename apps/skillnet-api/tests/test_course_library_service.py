"""Focused business-rule tests for folders and atomic course skills."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.exceptions import ConflictError, NotFoundError
from src.services.course_folder_service import CourseFolderService
from src.services.enrollment_service import EnrollmentService
from src.services.skill_service import SkillService


@pytest.mark.asyncio
async def test_folder_names_are_unique_case_insensitively() -> None:
    repo = SimpleNamespace(
        get_by_name=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))
    )

    with pytest.raises(ConflictError):
        await CourseFolderService(repo).create(org_id=uuid.uuid4(), name="Soporte")


@pytest.mark.asyncio
async def test_replace_course_skills_reuses_names_and_deduplicates(monkeypatch) -> None:
    org_id = uuid.uuid4()
    course_id = uuid.uuid4()
    existing = SimpleNamespace(id=uuid.uuid4(), name="Validar entradas")
    repo = SimpleNamespace(
        session=object(),
        get_by_name=AsyncMock(return_value=existing),
        get_scoped=AsyncMock(),
        create=AsyncMock(),
        replace_course_skills=AsyncMock(),
    )
    course_repo = SimpleNamespace(get_scoped=AsyncMock(return_value=object()))
    monkeypatch.setattr(
        "src.repositories.course_repo.CourseRepository", lambda session: course_repo
    )

    result = await SkillService(repo).replace_course_skills(
        org_id=org_id,
        course_id=course_id,
        items=[
            {"id": None, "name": existing.name, "description": None},
            {"id": None, "name": existing.name, "description": None},
        ],
    )

    assert result == [existing]
    repo.replace_course_skills.assert_awaited_once_with(course_id, [existing])
    repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_replace_course_skills_rejects_foreign_skill(monkeypatch) -> None:
    course_repo = SimpleNamespace(get_scoped=AsyncMock(return_value=object()))
    monkeypatch.setattr(
        "src.repositories.course_repo.CourseRepository", lambda session: course_repo
    )
    repo = SimpleNamespace(
        session=object(),
        get_scoped=AsyncMock(return_value=None),
    )
    skill_id = uuid.uuid4()

    with pytest.raises(NotFoundError):
        await SkillService(repo).replace_course_skills(
            org_id=uuid.uuid4(),
            course_id=uuid.uuid4(),
            items=[{"id": skill_id, "name": None, "description": None}],
        )


@pytest.mark.asyncio
async def test_assign_courses_is_idempotent_across_a_folder() -> None:
    org_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    user_id = uuid.uuid4()
    first_course_id = uuid.uuid4()
    second_course_id = uuid.uuid4()
    existing = SimpleNamespace(id=uuid.uuid4())
    created = SimpleNamespace(id=uuid.uuid4())
    enrollment_repo = SimpleNamespace(
        session=object(),
        get_by_user_and_course=AsyncMock(side_effect=[existing, None]),
        create=AsyncMock(return_value=created),
    )
    course_repo = SimpleNamespace(get_scoped=AsyncMock(return_value=object()))
    exercise_repo = SimpleNamespace()

    enrollments, skipped = await EnrollmentService(
        enrollment_repo,
        course_repo,
        exercise_repo,
        lesson_progress_repo=SimpleNamespace(),
    ).assign_courses(
        org_id=org_id,
        assigned_by=admin_id,
        course_ids=[first_course_id, second_course_id],
        user_ids=[user_id],
        deadline=None,
    )

    assert enrollments == [created]
    assert skipped == 1
    assert course_repo.get_scoped.await_count == 2
    enrollment_repo.create.assert_awaited_once()
