"""Exercise + attempt data access."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.sql.elements import ColumnElement

from src.models import Exercise, ExerciseAttempt, Lesson, Module
from src.repositories.base import BaseRepository


class ExerciseRepository(BaseRepository[Exercise]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Exercise)

    async def get_with_course(self, id: uuid.UUID) -> Exercise | None:
        """Load the exercise with lesson -> module -> course to resolve org/access."""
        query = (
            select(Exercise)
            .where(Exercise.id == id)
            .options(
                joinedload(Exercise.lesson)
                .joinedload(Lesson.module)
                .joinedload(Module.course)
            )
        )
        return (await self.session.execute(query)).unique().scalar_one_or_none()

    async def list_attempts(
        self, *, exercise_id: uuid.UUID, user_id: uuid.UUID
    ) -> Sequence[ExerciseAttempt]:
        filters: list[ColumnElement[bool]] = [
            ExerciseAttempt.exercise_id == exercise_id,
            ExerciseAttempt.user_id == user_id,
        ]
        query = (
            select(ExerciseAttempt)
            .where(*filters)
            .order_by(ExerciseAttempt.attempted_at.desc())
        )
        return (await self.session.execute(query)).scalars().all()

    async def passed_exercise_ids(
        self, *, user_id: uuid.UUID, exercise_ids: list[uuid.UUID]
    ) -> set[uuid.UUID]:
        """Subset of ``exercise_ids`` the user has at least one passing attempt for."""
        if not exercise_ids:
            return set()
        query = select(ExerciseAttempt.exercise_id).where(
            ExerciseAttempt.user_id == user_id,
            ExerciseAttempt.exercise_id.in_(exercise_ids),
            ExerciseAttempt.passed.is_(True),
        )
        return set((await self.session.execute(query)).scalars().all())
