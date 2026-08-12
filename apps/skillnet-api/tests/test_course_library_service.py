"""Focused business-rule tests for folders and atomic course skills."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.exceptions import ConflictError, NotFoundError
from src.services.course_folder_service import CourseFolderService
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
