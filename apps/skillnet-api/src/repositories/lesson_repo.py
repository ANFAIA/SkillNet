"""Lesson data access, including eager-loading for org-scoped updates."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.models import Lesson, Module
from src.repositories.base import BaseRepository


class LessonRepository(BaseRepository[Lesson]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Lesson)

    async def get_with_course(self, id: uuid.UUID) -> Lesson | None:
        """Load the lesson with module -> course to resolve org/status checks."""
        query = (
            select(Lesson)
            .where(Lesson.id == id)
            .options(
                joinedload(Lesson.module).joinedload(Module.course)
            )
        )
        return (await self.session.execute(query)).unique().scalar_one_or_none()
