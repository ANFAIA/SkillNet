"""Cross-organisation isolation for enrollments (§ tenant defence).

The confirmed bug: a learner of org A was enrolled into a course of org B. The
listing scoped only by the *learner's* org, so the row surfaced in that learner's
"My Courses" (title visible) and then 404'd when opened, because course-detail is
scoped to the caller's org. This test seeds exactly that mismatched row directly —
simulating a pre-existing bad record — and asserts the repository never lists it,
without the row being deleted. It complements the unit tests in
``test_course_library_service.py`` that cover the write path (create) rejection.
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
async def test_a_cross_org_enrollment_is_never_listed_for_the_learner() -> None:
    suffix = uuid.uuid4().hex[:8]
    async with async_session_factory() as db:
        org_a = Organization(name=f"A {suffix}", slug=f"a-{suffix}", settings={})
        org_b = Organization(name=f"B {suffix}", slug=f"b-{suffix}", settings={})
        db.add_all([org_a, org_b])
        await db.flush()

        learner_a = User(
            org_id=org_a.id,
            email=f"learner-{suffix}@iso.example",
            hashed_password="x",
            full_name="Learner A",
            role=UserRole.EMPLOYEE,
            is_active=True,
        )
        admin_b = User(
            org_id=org_b.id,
            email=f"admin-{suffix}@iso.example",
            hashed_password="x",
            full_name="Admin B",
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add_all([learner_a, admin_b])
        await db.flush()

        course_b = Course(
            org_id=org_b.id,
            title="Recuperar entradas",
            created_by=admin_b.id,
            status=ContentStatus.PUBLISHED,
        )
        db.add(course_b)
        await db.flush()

        # The illegal row: learner in org A, course in org B.
        bad = Enrollment(
            user_id=learner_a.id,
            course_id=course_b.id,
            assigned_by=admin_b.id,
        )
        db.add(bad)
        await db.commit()

        repo = EnrollmentRepository(db)
        # Listed from org A (the learner's org): the course lives in org B, so nothing.
        rows_a, total_a = await repo.list_enrollments(org_id=org_a.id, user_id=learner_a.id)
        # Listed from org B (the course's org): the learner lives in org A, so nothing.
        rows_b, total_b = await repo.list_enrollments(org_id=org_b.id, user_id=learner_a.id)

        assert total_a == 0 and list(rows_a) == []
        assert total_b == 0 and list(rows_b) == []

        # The row still exists — isolation hides it, it does not delete it.
        still_there = await repo.get_by_user_and_course(learner_a.id, course_b.id)
        assert still_there is not None

        # Cleanup.
        await db.delete(bad)
        await db.delete(course_b)
        await db.delete(learner_a)
        await db.delete(admin_b)
        await db.delete(org_a)
        await db.delete(org_b)
        await db.commit()
