"""Lesson-progress data access."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.lesson_progress import LessonProgress
from src.repositories.base import BaseRepository


class LessonProgressRepository(BaseRepository[LessonProgress]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, LessonProgress)

    async def get_by_user_and_lesson(
        self, user_id: uuid.UUID, lesson_id: uuid.UUID
    ) -> LessonProgress | None:
        query = select(LessonProgress).where(
            LessonProgress.user_id == user_id,
            LessonProgress.lesson_id == lesson_id,
        )
        return (await self.session.execute(query)).scalar_one_or_none()

    async def completed_lesson_ids(
        self, *, user_id: uuid.UUID, lesson_ids: list[uuid.UUID]
    ) -> set[uuid.UUID]:
        """Return the subset of ``lesson_ids`` the user has completed."""
        if not lesson_ids:
            return set()
        query = select(LessonProgress.lesson_id).where(
            LessonProgress.user_id == user_id,
            LessonProgress.lesson_id.in_(lesson_ids),
        )
        return set((await self.session.execute(query)).scalars().all())
