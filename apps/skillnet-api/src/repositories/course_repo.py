"""Course data access, including nested eager-loading for detail views."""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from src.models import (
    ContentStatus,
    Course,
    CourseArtifactGenerator,
    CourseGenerationState,
    CourseNode,
    Enrollment,
    EnrollmentStatus,
    Lesson,
    Module,
)
from src.repositories.base import BaseRepository


class CourseRepository(BaseRepository[Course]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Course)

    async def get_scoped(self, id: uuid.UUID, org_id: uuid.UUID) -> Course | None:
        """One course of this org, with ``folder`` already loaded.

        The eager load is not decoration. This is the read behind every write route
        (``PUT /courses/{id}``, archive, unarchive), and those routes project the course
        with the same synchronous helpers as ``GET``, which read ``course.folder`` to
        fill ``folder_name``. ``session.get`` leaves the relationship unloaded, so the
        response came back with a correct ``folder_id`` and ``folder_name: null`` — and
        a lazy load from a sync projector after ``await db.commit()`` would raise
        ``MissingGreenlet`` instead. Loading it here, awaited, is what makes the two
        projections agree.
        """
        query = (
            select(Course)
            .where(Course.id == id, Course.org_id == org_id)
            .options(selectinload(Course.folder))
        )
        return (await self.session.execute(query)).scalar_one_or_none()

    async def list_courses(
        self,
        *,
        org_id: uuid.UUID,
        status: ContentStatus | None = None,
        search: str | None = None,
        folder_id: uuid.UUID | None = None,
        unorganized: bool = False,
        generation_state: CourseGenerationState | None = None,
        include_archived: bool = True,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[tuple[Course, int, int]], int]:
        """Return ``(course, module_count, node_count)`` triples plus the total.

        ``include_archived=False`` drops the archived courses, and only when no explicit
        ``status`` was asked for: a caller that asked for one status already said which
        rows it wants, and letting the flag also apply there would make
        ``status=archived, include_archived=False`` an unanswerable question.
        """
        filters: list[ColumnElement[bool]] = [Course.org_id == org_id]
        if status is not None:
            filters.append(Course.status == status)
        elif not include_archived:
            filters.append(Course.status != ContentStatus.ARCHIVED)
        if generation_state is not None:
            filters.append(Course.generation_state == generation_state)
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    Course.title.ilike(pattern),
                    Course.description.ilike(pattern),
                    Course.outcome.ilike(pattern),
                )
            )
        if folder_id is not None:
            filters.append(Course.folder_id == folder_id)
        elif unorganized:
            filters.append(Course.folder_id.is_(None))

        count_query = select(func.count()).select_from(Course)
        query = (
            select(
                Course,
                func.count(distinct(Module.id)),
                func.count(distinct(CourseNode.id)),
            )
            .outerjoin(Module, Module.course_id == Course.id)
            .outerjoin(CourseNode, CourseNode.course_id == Course.id)
            .options(selectinload(Course.folder))
            .group_by(Course.id)
            .order_by(Course.created_at.desc())
        )
        for f in filters:
            count_query = count_query.where(f)
            query = query.where(f)

        total = (await self.session.execute(count_query)).scalar_one()
        result = await self.session.execute(query.offset(offset).limit(limit))
        return [(row[0], row[1], row[2]) for row in result.all()], total

    async def count_enrollments(self, course_id: uuid.UUID) -> tuple[int, int]:
        """``(total, completed)`` enrollments of one course, in a single round trip.

        Counted rather than loaded: the caller is :meth:`CourseService.delete`, which
        needs the size of what it is about to destroy for the audit row, not the rows
        themselves. A course assigned to a whole company has thousands of them.
        """
        query = select(
            func.count(),
            func.count().filter(Enrollment.status == EnrollmentStatus.COMPLETED),
        ).where(Enrollment.course_id == course_id)
        total, completed = (await self.session.execute(query)).one()
        return int(total), int(completed)

    async def get_detail(self, id: uuid.UUID, org_id: uuid.UUID) -> Course | None:
        """Eager-load modules -> lessons -> exercises, ordered by position."""
        query = (
            select(Course)
            .where(Course.id == id, Course.org_id == org_id)
            .options(
                selectinload(Course.modules)
                .selectinload(Module.lessons)
                .selectinload(Lesson.exercises)
                ,
                selectinload(Course.folder),
            )
        )
        return (await self.session.execute(query)).scalar_one_or_none()

    async def count_active_nodes(self, course_id: uuid.UUID) -> int:
        query = select(func.count()).select_from(CourseNode).where(
            CourseNode.course_id == course_id,
            CourseNode.archived.is_(False),
        )
        return (await self.session.execute(query)).scalar_one()

    async def list_artifact_generator_ids(self, course_id: uuid.UUID) -> list[uuid.UUID]:
        query = select(CourseArtifactGenerator.user_id).where(
            CourseArtifactGenerator.course_id == course_id
        )
        return list((await self.session.execute(query)).scalars().all())

    async def replace_artifact_generators(
        self, course_id: uuid.UUID, user_ids: list[uuid.UUID]
    ) -> None:
        await self.session.execute(
            delete(CourseArtifactGenerator).where(
                CourseArtifactGenerator.course_id == course_id
            )
        )
        for user_id in dict.fromkeys(user_ids):
            self.session.add(
                CourseArtifactGenerator(course_id=course_id, user_id=user_id)
            )
        await self.session.flush()
