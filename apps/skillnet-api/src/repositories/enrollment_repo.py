"""Enrollment data access."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from src.models import ContentStatus, Course, Enrollment, User
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

    async def existing_pairs(
        self,
        course_ids: Sequence[uuid.UUID],
        user_ids: Sequence[uuid.UUID],
    ) -> set[tuple[uuid.UUID, uuid.UUID]]:
        """Which ``(user_id, course_id)`` of this cross-product already exist.

        One query for the whole batch. ``assign_courses`` used to ask
        ``get_by_user_and_course`` once per pair, which is fine for one course and a
        handful of people and is 2 000 round-trips for a folder assigned to a group.
        Knowing the answer up front turns the loop's read half into a set lookup and
        leaves the write half — the SAVEPOINT that survives the insert race — untouched.

        Not a substitute for that savepoint: this snapshot can be stale by the time the
        insert runs, so a pair it reports as missing may still collide. That collision
        is handled where it always was.
        """
        if not course_ids or not user_ids:
            return set()
        stmt = select(Enrollment.user_id, Enrollment.course_id).where(
            Enrollment.course_id.in_(set(course_ids)),
            Enrollment.user_id.in_(set(user_ids)),
        )
        return {(row[0], row[1]) for row in (await self.session.execute(stmt)).all()}

    async def list_with_courses(
        self, ids: Sequence[uuid.UUID]
    ) -> list[Enrollment]:
        """Load these enrollments with their course, in one query.

        The assignment routes echo back what they just created, and ``_read`` needs the
        ``course`` relationship. Doing that one ``get_with_course`` at a time made the
        echo cost one round-trip per created row — invisible for one course and three
        people, and the dominant cost of assigning a folder to a group.
        """
        if not ids:
            return []
        stmt = (
            select(Enrollment)
            .where(Enrollment.id.in_(set(ids)))
            .options(selectinload(Enrollment.course))
        )
        return list((await self.session.scalars(stmt)).all())

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
        user_ids: Sequence[uuid.UUID] | None = None,
        course_id: uuid.UUID | None = None,
        course_ids: Sequence[uuid.UUID] | None = None,
        status: object | None = None,
        include_archived_courses: bool = True,
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
        # The plural forms answer one question the singulars cannot: "of these people, in
        # these courses, who holds what". A screen showing a page of 20 people and a
        # folder of 8 courses would otherwise need 8 unfiltered reads capped at 100 rows
        # each and would silently miss anybody past the hundredth — which is how a tick
        # comes to say "not enrolled" about somebody who is.
        #
        # An *empty* list is not "no filter": it is "none of them", and it must answer
        # nothing. `None` is the absent filter.
        if user_ids is not None:
            filters.append(Enrollment.user_id.in_(list(user_ids)))
        if course_id is not None:
            filters.append(Enrollment.course_id == course_id)
        if course_ids is not None:
            filters.append(Enrollment.course_id.in_(list(course_ids)))
        if status is not None:
            filters.append(Enrollment.status == status)
        # Archiving a course means "stop showing it to the learners", so an enrollment
        # into an archived course must drop out of the learner's own list. It is a
        # parameter and not an unconditional filter because this method has callers on
        # both sides of that sentence:
        #   - `GET /enrollments` (routes/enrollments.py) is *both* surfaces: a learner
        #     asking for their own courses (excludes archived) and an admin opening
        #     somebody's record (includes them — "you were enrolled in this, and it is
        #     archived now" is history the admin needs, and hiding it would make the
        #     drawer look emptier than the database is).
        #   - the admin agent tools `enrollment_list` / `users_get_progress`
        #     (services/agent_tools/) answer the same admin questions in words.
        #   - the §7.5 closure recomputes (`course_schema_service.recompute…` and
        #     `enrollment_service`) pass an explicit `course_id` and must see every row
        #     of that course whatever its status: enrollment status is a function of the
        #     current schema, and skipping archived courses would freeze it mid-way.
        # Hence: default = show everything (what every admin/internal caller wants), and
        # the learner surface opts out explicitly.
        if not include_archived_courses:
            filters.append(Course.status != ContentStatus.ARCHIVED)

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
