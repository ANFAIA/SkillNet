"""Persistence for the intentionally flat course-folder library."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import ContentStatus, Course, CourseFolder
from src.repositories.base import BaseRepository


class CourseFolderRepository(BaseRepository[CourseFolder]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, CourseFolder)

    async def get_scoped(
        self, folder_id: uuid.UUID, org_id: uuid.UUID
    ) -> CourseFolder | None:
        stmt = select(CourseFolder).where(
            CourseFolder.id == folder_id, CourseFolder.org_id == org_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_name(self, org_id: uuid.UUID, name: str) -> CourseFolder | None:
        stmt = select(CourseFolder).where(
            CourseFolder.org_id == org_id,
            func.lower(CourseFolder.name) == name.casefold(),
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_with_counts(
        self, org_id: uuid.UUID
    ) -> Sequence[tuple[CourseFolder, int]]:
        stmt = (
            select(CourseFolder, func.count(Course.id))
            .outerjoin(Course, Course.folder_id == CourseFolder.id)
            .where(CourseFolder.org_id == org_id)
            .group_by(CourseFolder.id)
            .order_by(func.lower(CourseFolder.name))
        )
        return list((await self.session.execute(stmt)).tuples().all())

    async def list_published_course_ids(
        self, folder_id: uuid.UUID, org_id: uuid.UUID
    ) -> Sequence[uuid.UUID]:
        stmt = (
            select(Course.id)
            .where(
                Course.org_id == org_id,
                Course.folder_id == folder_id,
                Course.status == ContentStatus.PUBLISHED,
            )
            .order_by(Course.created_at, Course.id)
        )
        return list((await self.session.scalars(stmt)).all())
