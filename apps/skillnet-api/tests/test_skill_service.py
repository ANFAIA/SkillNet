"""Unit tests for SkillService (pure logic, mocked repo)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.user_skill import SkillLevel


def _make_user(name: str, org_id: uuid.UUID) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.org_id = org_id
    user.full_name = name
    user.email = f"{name.lower().replace(' ', '.')}@test.com"
    return user


def _make_skill(name: str, org_id: uuid.UUID, category_name: str = "General") -> MagicMock:
    skill = MagicMock()
    skill.id = uuid.uuid4()
    skill.org_id = org_id
    skill.name = name
    skill.description = None
    category = MagicMock()
    category.name = category_name
    skill.category = category
    return skill


def _make_user_skill(user, skill, level: SkillLevel) -> MagicMock:
    us = MagicMock()
    us.user_id = user.id
    us.skill_id = skill.id
    us.level = level
    us.source = "manual"
    us.user = user
    us.skill = skill
    return us


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def repo():
    repo = AsyncMock()
    return repo


@pytest.fixture
def service(repo):
    from src.services.skill_service import SkillService
    return SkillService(repo)


@pytest.mark.asyncio
async def test_who_knows_returns_matching_users(service, repo, org_id):
    """who_knows should return users with the skill."""
    user1 = _make_user("Maria", org_id)
    user2 = _make_user("Juan", org_id)
    skill = _make_skill("Python", org_id)

    repo.who_knows.return_value = [
        (user1, SkillLevel.HIGH),
        (user2, SkillLevel.MEDIUM),
    ]

    result = await service.who_knows(org_id, "Python")

    repo.who_knows.assert_awaited_once()
    assert len(result) == 2


@pytest.mark.asyncio
async def test_who_knows_empty(service, repo, org_id):
    """who_knows should return empty list when no one has the skill."""
    repo.who_knows.return_value = []

    result = await service.who_knows(org_id, "Nonexistent")

    assert result == []


@pytest.mark.asyncio
async def test_list_skills(service, repo, org_id):
    """list_skills should return skills from repo."""
    skill1 = _make_skill("Python", org_id, "Tech")
    skill2 = _make_skill("SQL", org_id, "Tech")
    repo.list_skills.return_value = [skill1, skill2]

    result = await service.list_skills(org_id)

    repo.list_skills.assert_awaited_once_with(org_id)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_get_user_skills(service, repo, org_id):
    """get_user_skills should return all skills for a user."""
    user = _make_user("Maria", org_id)
    skill = _make_skill("Python", org_id)
    us = _make_user_skill(user, skill, SkillLevel.HIGH)

    repo.get_user_skills.return_value = [us]

    result = await service.get_user_skills(org_id, user.id)

    repo.get_user_skills.assert_awaited_once()
    assert len(result) == 1


@pytest.mark.asyncio
async def test_get_gap(service, repo, org_id):
    """get_gap should return gap analysis."""
    repo.get_gaps.return_value = [
        {"skill_name": "Python", "total": 10, "high": 1, "medium": 2, "low": 3, "none": 4},
    ]

    result = await service.get_gap(org_id)

    repo.get_gaps.assert_awaited_once()
    assert len(result) >= 1
