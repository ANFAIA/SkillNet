"""Skill business logic: taxonomy, who-knows, gap analysis, and verification."""

import uuid

from src.core.exceptions import NotFoundError, ValidationError
from src.models.user_skill import SkillLevel
from src.repositories.skill_repo import SkillRepository


def _to_level(value: str) -> SkillLevel:
    try:
        return SkillLevel(value)
    except ValueError as exc:
        raise ValidationError(f"Invalid skill level: {value}", field="level") from exc


class SkillService:
    def __init__(self, repo: SkillRepository) -> None:
        self.repo = repo

    async def list_skills(self, org_id: uuid.UUID) -> list[dict]:
        """Return the full skill taxonomy grouped by category."""
        categories = await self.repo.list_skills(org_id)
        result = []
        for cat in categories:
            result.append(
                {
                    "id": getattr(cat, "id", None),
                    "name": cat.name,
                    "position": cat.position,
                    "skills": [
                        {
                            "id": s.id,
                            "name": s.name,
                            "description": s.description,
                        }
                        for s in cat.skills
                    ],
                }
            )
        return result

    async def who_knows(
        self,
        org_id: uuid.UUID,
        skill_name: str,
        min_level: str | None = None,
    ) -> list[dict]:
        """Find employees who possess a given skill."""
        level_enum = _to_level(min_level) if min_level else None
        rows = await self.repo.who_knows(org_id, skill_name, level_enum)
        return [
            {
                "user_id": user.id,
                "full_name": user.full_name,
                "email": user.email,
                "level": level.value,
            }
            for user, level in rows
        ]

    async def get_gap(self, org_id: uuid.UUID) -> list[dict]:
        """Return gap analysis for every skill in the org."""
        return await self.repo.get_gaps(org_id)

    async def verify_skill(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        skill_name: str,
        level: str,
        source: str,
    ) -> dict:
        """Create or update a user's proficiency for a skill.

        If the skill does not exist yet, it is created automatically.
        """
        level_enum = _to_level(level)

        skill = await self.repo.get_by_name(org_id, skill_name)
        if skill is None:
            skill = await self.repo.create(org_id=org_id, name=skill_name)

        user_skill = await self.repo.upsert_user_skill(
            user_id=user_id,
            skill_id=skill.id,
            level=level_enum,
            source=source,
        )
        return {
            "user_skill_id": user_skill.id,
            "user_id": user_skill.user_id,
            "skill_id": user_skill.skill_id,
            "skill_name": skill.name,
            "level": user_skill.level.value,
            "source": user_skill.source,
        }

    async def get_user_skills(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[dict]:
        """Return all skills for a given user."""
        user_skills = await self.repo.get_user_skills(org_id, user_id)
        return [
            {
                "id": us.id,
                "skill_id": us.skill_id,
                "skill_name": us.skill.name,
                "level": us.level.value,
                "source": us.source,
                "last_assessed_at": us.last_assessed_at,
            }
            for us in user_skills
        ]
