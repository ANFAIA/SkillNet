"""Skill data access: taxonomy, who-knows, gap analysis, and user-skill upsert."""

import uuid
from collections.abc import Sequence

from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.skill import Skill
from src.models.course import Course
from src.models.course_skill import CourseSkill
from src.models.skill_category import SkillCategory
from src.models.user import User
from src.models.user_skill import SkillLevel, UserSkill
from src.repositories.base import BaseRepository

# Ordering map for level comparisons.
_LEVEL_ORDER = {SkillLevel.LOW: 0, SkillLevel.MEDIUM: 1, SkillLevel.HIGH: 2}


class SkillRepository(BaseRepository[Skill]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Skill)

    # ------------------------------------------------------------------
    # Taxonomy
    # ------------------------------------------------------------------

    async def list_skills(self, org_id: uuid.UUID) -> Sequence[SkillCategory]:
        """Return all categories (with their skills) for an org.

        Skills without a category are collected under a virtual *None* category
        entry; callers must handle that.
        """
        stmt = (
            select(SkillCategory)
            .where(SkillCategory.org_id == org_id)
            .options(selectinload(SkillCategory.skills))
            .order_by(SkillCategory.position)
        )
        result = await self.session.execute(stmt)
        categories = list(result.scalars().all())

        # Also fetch uncategorized skills.
        uncategorized_stmt = (
            select(Skill)
            .where(Skill.org_id == org_id, Skill.category_id.is_(None))
            .order_by(Skill.name)
        )
        uncategorized = (await self.session.execute(uncategorized_stmt)).scalars().all()

        # Return categories; the caller can inspect uncategorized separately.
        # We attach uncategorized skills as a synthetic category with id=None.
        if uncategorized:
            synthetic = SkillCategory(
                org_id=org_id, name="Uncategorized", position=-1
            )
            # Bypass the ORM relationship setter: just set the list directly.
            synthetic.skills = list(uncategorized)  # type: ignore[assignment]
            categories.insert(0, synthetic)

        return categories

    async def get_by_name(self, org_id: uuid.UUID, name: str) -> Skill | None:
        stmt = select(Skill).where(
            Skill.org_id == org_id, func.lower(Skill.name) == name.casefold()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_scoped(self, skill_id: uuid.UUID, org_id: uuid.UUID) -> Skill | None:
        stmt = select(Skill).where(Skill.id == skill_id, Skill.org_id == org_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_flat(
        self,
        *,
        org_id: uuid.UUID,
        search: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[Skill], int]:
        filters = [Skill.org_id == org_id]
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(Skill.name.ilike(pattern))
        count = (
            await self.session.execute(
                select(func.count()).select_from(Skill).where(*filters)
            )
        ).scalar_one()
        stmt = (
            select(Skill)
            .where(*filters)
            .order_by(func.lower(Skill.name))
            .offset(offset)
            .limit(limit)
        )
        return (await self.session.execute(stmt)).scalars().all(), count

    async def list_for_course(
        self, course_id: uuid.UUID, org_id: uuid.UUID
    ) -> Sequence[Skill]:
        stmt = (
            select(Skill)
            .join(CourseSkill, CourseSkill.skill_id == Skill.id)
            .join(Course, Course.id == CourseSkill.course_id)
            .where(Course.id == course_id, Course.org_id == org_id)
            .order_by(func.lower(Skill.name))
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def replace_course_skills(
        self, course_id: uuid.UUID, skills: Sequence[Skill]
    ) -> None:
        await self.session.execute(
            delete(CourseSkill).where(CourseSkill.course_id == course_id)
        )
        self.session.add_all(
            [CourseSkill(course_id=course_id, skill_id=skill.id) for skill in skills]
        )
        await self.session.flush()

    async def usage_count(self, skill_id: uuid.UUID) -> int:
        course_count = (
            await self.session.execute(
                select(func.count()).select_from(CourseSkill).where(
                    CourseSkill.skill_id == skill_id
                )
            )
        ).scalar_one()
        user_count = (
            await self.session.execute(
                select(func.count()).select_from(UserSkill).where(
                    UserSkill.skill_id == skill_id
                )
            )
        ).scalar_one()
        return course_count + user_count

    # ------------------------------------------------------------------
    # Who-knows
    # ------------------------------------------------------------------

    async def who_knows(
        self,
        org_id: uuid.UUID,
        skill_name: str,
        min_level: SkillLevel | None = None,
    ) -> list[tuple[User, SkillLevel]]:
        """Return users who have *skill_name*, optionally filtered by min level."""
        level_case = case(
            (UserSkill.level == SkillLevel.LOW, 0),
            (UserSkill.level == SkillLevel.MEDIUM, 1),
            (UserSkill.level == SkillLevel.HIGH, 2),
        )

        stmt = (
            select(User, UserSkill.level)
            .join(UserSkill, UserSkill.user_id == User.id)
            .join(Skill, Skill.id == UserSkill.skill_id)
            .where(Skill.org_id == org_id, Skill.name == skill_name)
        )

        if min_level is not None:
            min_ord = _LEVEL_ORDER[min_level]
            stmt = stmt.where(level_case >= min_ord)

        stmt = stmt.order_by(level_case.desc(), User.full_name)

        result = await self.session.execute(stmt)
        return list(result.tuples().all())

    # ------------------------------------------------------------------
    # Gap analysis
    # ------------------------------------------------------------------

    async def get_gaps(
        self, org_id: uuid.UUID
    ) -> list[dict]:
        """For every skill in the org, count users at each level.

        Returns a list of dicts:
            {"skill_name": str, "total_users": int,
             "low": int, "medium": int, "high": int}
        """
        stmt = (
            select(
                Skill.name.label("skill_name"),
                func.count(UserSkill.id).label("total_users"),
                func.count()
                .filter(UserSkill.level == SkillLevel.LOW)
                .label("low"),
                func.count()
                .filter(UserSkill.level == SkillLevel.MEDIUM)
                .label("medium"),
                func.count()
                .filter(UserSkill.level == SkillLevel.HIGH)
                .label("high"),
            )
            .outerjoin(UserSkill, UserSkill.skill_id == Skill.id)
            .where(Skill.org_id == org_id)
            .group_by(Skill.id, Skill.name)
            .order_by(Skill.name)
        )

        result = await self.session.execute(stmt)
        return [
            {
                "skill_name": row.skill_name,
                "total_users": row.total_users,
                "low": row.low,
                "medium": row.medium,
                "high": row.high,
            }
            for row in result.all()
        ]

    # ------------------------------------------------------------------
    # User skills
    # ------------------------------------------------------------------

    async def get_user_skills(
        self, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> Sequence[UserSkill]:
        stmt = (
            select(UserSkill)
            .join(Skill, Skill.id == UserSkill.skill_id)
            .where(Skill.org_id == org_id, UserSkill.user_id == user_id)
            .options(selectinload(UserSkill.skill))
            .order_by(Skill.name)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def upsert_user_skill(
        self,
        user_id: uuid.UUID,
        skill_id: uuid.UUID,
        level: SkillLevel,
        source: str,
    ) -> UserSkill:
        """Insert or update a user-skill association."""
        stmt = select(UserSkill).where(
            UserSkill.user_id == user_id, UserSkill.skill_id == skill_id
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing is not None:
            existing.level = level
            existing.source = source
            await self.session.flush()
            return existing

        user_skill = UserSkill(
            user_id=user_id,
            skill_id=skill_id,
            level=level,
            source=source,
        )
        self.session.add(user_skill)
        await self.session.flush()
        return user_skill
