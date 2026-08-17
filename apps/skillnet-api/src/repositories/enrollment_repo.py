"""Enrollment data access."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from src.models import Course, Enrollment, User
from src.repositories.base import BaseRepository


class EnrollmentRepository(BaseRepository[Enrollment]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Enrollment)

    async def get_by_user_and_course(
        self, user_id: uuid.UUID, course_id: uuid.UUID
    ) -> Enrollment | None:
        query = select(Enrollment).where(
            Enrollment.user_id == user_id, Enrollment.course_id == course_id
        )
        return (await self.session.execute(query)).scalar_one_or_none()

    async def get_with_course(self, id: uuid.UUID) -> Enrollment | None:
        query = (
            select(Enrollment)
            .where(Enrollment.id == id)
            .options(selectinload(Enrollment.course))
        )
        return (await self.session.execute(query)).scalar_one_or_none()

    async def list_enrollments(
        self,
        *,
        org_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        course_id: uuid.UUID | None = None,
        status: object | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[Enrollment], int]:
        # Org scope requires BOTH ends of the enrollment to live in this org: the
        # learner (User.org_id) and the course (Course.org_id). Scoping by the user
        # alone let a cross-org enrollment — a learner of org A enrolled into a course
        # of org B — surface in the learner's "My Courses", where its title showed but
        # the course-detail route (correctly scoped to the caller's org) then answered
        # 404 ("Curso no encontrado"). Requiring the course's org too keeps such a row
        # from ever listing, without deleting it.
        filters: list[ColumnElement[bool]] = [
            User.org_id == org_id,
            Course.org_id == org_id,
        ]
        if user_id is not None:
            filters.append(Enrollment.user_id == user_id)
        if course_id is not None:
            filters.append(Enrollment.course_id == course_id)
        if status is not None:
            filters.append(Enrollment.status == status)

        base = (
            select(Enrollment)
            .join(User, User.id == Enrollment.user_id)
            .join(Course, Course.id == Enrollment.course_id)
        )
        query = (
            base.where(*filters)
            .options(selectinload(Enrollment.course))
            .order_by(Enrollment.created_at.desc())
        )
        count_query = (
            select(func.count())
            .select_from(Enrollment)
            .join(User, User.id == Enrollment.user_id)
            .join(Course, Course.id == Enrollment.course_id)
            .where(*filters)
        )
        total = (await self.session.execute(count_query)).scalar_one()
        rows = (
            (await self.session.execute(query.offset(offset).limit(limit)))
            .scalars()
            .all()
        )
        return rows, total

    async def course_for_enrollment(self, enrollment: Enrollment) -> Course:
        return await self.session.get(Course, enrollment.course_id)  # type: ignore[return-value]
