"""Course data access, including nested eager-loading for detail views."""

import uuid
from collections.abc import Sequence

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from src.models import ContentStatus, Course, CourseNode, Lesson, Module
from src.repositories.base import BaseRepository


class CourseRepository(BaseRepository[Course]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Course)

    async def get_scoped(self, id: uuid.UUID, org_id: uuid.UUID) -> Course | None:
        course = await self.get_by_id(id)
        if course is None or course.org_id != org_id:
            return None
        return course

    async def list_courses(
        self,
        *,
        org_id: uuid.UUID,
        status: ContentStatus | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[tuple[Course, int, int]], int]:
        """Return ``(course, module_count, node_count)`` triples plus the total."""
        filters: list[ColumnElement[bool]] = [Course.org_id == org_id]
        if status is not None:
            filters.append(Course.status == status)

        count_query = select(func.count()).select_from(Course)
        query = (
            select(
                Course,
                func.count(distinct(Module.id)),
                func.count(distinct(CourseNode.id)),
            )
            .outerjoin(Module, Module.course_id == Course.id)
            .outerjoin(CourseNode, CourseNode.course_id == Course.id)
            .group_by(Course.id)
            .order_by(Course.created_at.desc())
        )
        for f in filters:
            count_query = count_query.where(f)
            query = query.where(f)

        total = (await self.session.execute(count_query)).scalar_one()
        result = await self.session.execute(query.offset(offset).limit(limit))
        return [(row[0], row[1], row[2]) for row in result.all()], total

    async def get_detail(self, id: uuid.UUID, org_id: uuid.UUID) -> Course | None:
        """Eager-load modules -> lessons -> exercises, ordered by position."""
        query = (
            select(Course)
            .where(Course.id == id, Course.org_id == org_id)
            .options(
                selectinload(Course.modules)
                .selectinload(Module.lessons)
                .selectinload(Lesson.exercises)
            )
        )
        return (await self.session.execute(query)).scalar_one_or_none()

    async def get_with_enrollments(
        self, id: uuid.UUID, org_id: uuid.UUID
    ) -> Course | None:
        query = (
            select(Course)
            .where(Course.id == id, Course.org_id == org_id)
            .options(selectinload(Course.enrollments))
        )
        return (await self.session.execute(query)).scalar_one_or_none()
