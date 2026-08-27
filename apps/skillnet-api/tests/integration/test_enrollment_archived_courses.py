"""An archived course drops out of the learner's list — the SQL half of it.

`tests/test_course_archive.py` pins the decision (`GET /enrollments` asks for the
exclusion for a learner and not for an admin). This pins the query that has to honour
it: `enrollment_repo.list_enrollments` joined `courses` only to check `Course.org_id`,
so `Course.status` never reached the WHERE clause and an archived course kept showing in
"My Courses" — with its rows, its count and its progress.

Both directions matter here: the filter must hide the archived course *and* leave the
live one alone, and the default (every admin surface, plus the §7.5 closure recomputes)
must keep seeing both.
"""

from __future__ import annotations

import uuid

import pytest

from src.deps.db import async_session_factory
from src.models import Course, Enrollment, Organization, User, UserRole
from src.models.course import ContentStatus
from src.repositories.enrollment_repo import EnrollmentRepository

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_an_archived_course_leaves_the_learners_list_but_not_the_admins() -> None:
    suffix = uuid.uuid4().hex[:8]
    async with async_session_factory() as db:
        org = Organization(name=f"Org {suffix}", slug=f"org-{suffix}", settings={})
        db.add(org)
        await db.flush()

        admin = User(
            org_id=org.id,
            email=f"admin-{suffix}@arch.example",
            hashed_password="x",
            full_name="Admin",
            role=UserRole.ADMIN,
            is_active=True,
        )
        learner = User(
            org_id=org.id,
            email=f"learner-{suffix}@arch.example",
            hashed_password="x",
            full_name="Learner",
            role=UserRole.EMPLOYEE,
            is_active=True,
        )
        db.add_all([admin, learner])
        await db.flush()

        live = Course(
            org_id=org.id,
            title="Cobro con tarjeta",
            created_by=admin.id,
            status=ContentStatus.PUBLISHED,
        )
        archived = Course(
            org_id=org.id,
            title="Cobro con cheque",
            created_by=admin.id,
            status=ContentStatus.ARCHIVED,
        )
        db.add_all([live, archived])
        await db.flush()

        rows = [
            Enrollment(user_id=learner.id, course_id=live.id, assigned_by=admin.id),
            Enrollment(user_id=learner.id, course_id=archived.id, assigned_by=admin.id),
        ]
        db.add_all(rows)
        await db.commit()

        repo = EnrollmentRepository(db)

        learner_rows, learner_total = await repo.list_enrollments(
            org_id=org.id, user_id=learner.id, include_archived_courses=False
        )
        assert learner_total == 1
        assert [row.course_id for row in learner_rows] == [live.id]

        admin_rows, admin_total = await repo.list_enrollments(
            org_id=org.id, user_id=learner.id
        )
        assert admin_total == 2
        assert {row.course_id for row in admin_rows} == {live.id, archived.id}

        # Hidden, never deleted: the enrollment into the archived course is still there,
        # with whatever progress it had, ready for `POST /courses/{id}/unarchive`.
        assert await repo.get_by_user_and_course(learner.id, archived.id) is not None

        for row in rows:
            await db.delete(row)
        await db.delete(live)
        await db.delete(archived)
        await db.delete(learner)
        await db.delete(admin)
        await db.delete(org)
        await db.commit()
