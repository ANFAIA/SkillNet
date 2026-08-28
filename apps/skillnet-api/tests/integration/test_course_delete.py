"""Deleting a course against a real schema: the cases that used to answer 500 or 409.

Every course produced by a generation run has a ``generation_jobs`` row pointing at it,
and until migration 0024 that foreign key had no ``ON DELETE``. ``DELETE /courses/{id}``
therefore raised ``ForeignKeyViolation`` for exactly the courses an admin most wants to
remove. ``enrollments.course_id`` was the last restrictive reference and it survived that
migration on purpose, because the service refused a course with enrollments; migration
0032 makes it ``CASCADE``, now that the refusal is gone.

Only a real database can prove the constraints behave: the unit suite in
``tests/test_course_delete.py`` covers the rules, the audit row and the file cleanup;
this covers the schema and the cascade.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from src.deps.db import async_session_factory
from src.models import (
    AuditLog,
    ChatSession,
    ContentStatus,
    Course,
    Enrollment,
    EnrollmentStatus,
    GenerationJob,
    Organization,
    User,
    UserRole,
)
from src.models.generation_job import GenerationOutput, GenerationStep
from src.repositories.course_repo import CourseRepository
from src.services.course_service import CourseService

pytestmark = pytest.mark.integration


async def _world(db, suffix: str) -> tuple[Organization, User]:
    org = Organization(name=f"Del {suffix}", slug=f"del-{suffix}", settings={})
    db.add(org)
    await db.flush()
    admin = User(
        org_id=org.id,
        email=f"admin-{suffix}@delete.example",
        hashed_password="x",
        full_name="Admin",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(admin)
    await db.flush()
    return org, admin


@pytest.mark.asyncio
async def test_a_draft_with_a_generation_job_is_deleted_and_the_job_survives() -> None:
    suffix = uuid.uuid4().hex[:8]
    async with async_session_factory() as db:
        org, admin = await _world(db, suffix)
        course = Course(
            org_id=org.id,
            title="Borrador abandonado",
            created_by=admin.id,
            status=ContentStatus.DRAFT,
        )
        db.add(course)
        await db.flush()
        job = GenerationJob(
            org_id=org.id,
            triggered_by=admin.id,
            output_type=GenerationOutput.COURSE_AND_MANUAL,
            status=GenerationStep.FAILED,
            result_course_id=course.id,
        )
        session = ChatSession(
            user_id=admin.id,
            org_id=org.id,
            agent_type="tutor",
            course_id=course.id,
        )
        db.add_all([job, session])
        await db.commit()
        course_id, job_id, session_id = course.id, job.id, session.id

        await CourseService(CourseRepository(db)).delete(
            course_id=course_id, org_id=org.id
        )
        await db.commit()

        assert await db.get(Course, course_id) is None
        # The audit trail survives; it just stops naming a course that is gone.
        assert (
            await db.execute(
                select(GenerationJob.result_course_id).where(GenerationJob.id == job_id)
            )
        ).scalar_one() is None
        assert (
            await db.execute(
                select(ChatSession.course_id).where(ChatSession.id == session_id)
            )
        ).scalar_one() is None

        await db.delete(await db.get(GenerationJob, job_id))
        await db.delete(await db.get(ChatSession, session_id))
        await db.delete(admin)
        await db.delete(org)
        await db.commit()


@pytest.mark.asyncio
async def test_a_published_course_with_enrollments_is_deleted_and_audited() -> None:
    """The case migration 0032 unlocked, end to end against the real constraints.

    Until then this raised ``ForeignKeyViolation`` on ``enrollments.course_id``, so the
    only thing a real database could prove about it was the refusal. What it has to prove
    now is the opposite and one thing more: the enrollments go with the course, and the
    ``audit_log`` row that outlives both says how many there were.
    """
    suffix = uuid.uuid4().hex[:8]
    async with async_session_factory() as db:
        org, admin = await _world(db, suffix)
        learners = []
        for index in range(2):
            learner = User(
                org_id=org.id,
                email=f"learner-{index}-{suffix}@delete.example",
                hashed_password="x",
                full_name=f"Learner {index}",
                role=UserRole.EMPLOYEE,
                is_active=True,
            )
            db.add(learner)
            learners.append(learner)
        await db.flush()
        course = Course(
            org_id=org.id,
            title="Curso con gente dentro",
            created_by=admin.id,
            status=ContentStatus.PUBLISHED,
        )
        db.add(course)
        await db.flush()
        enrollments = [
            Enrollment(
                user_id=learners[0].id, course_id=course.id, assigned_by=admin.id
            ),
            Enrollment(
                user_id=learners[1].id,
                course_id=course.id,
                assigned_by=admin.id,
                status=EnrollmentStatus.COMPLETED,
            ),
        ]
        db.add_all(enrollments)
        await db.commit()
        course_id = course.id
        enrollment_ids = [enrollment.id for enrollment in enrollments]

        await CourseService(CourseRepository(db)).delete(
            course_id=course_id, org_id=org.id, actor_id=admin.id
        )
        await db.commit()

        assert await db.get(Course, course_id) is None
        # Counted with a query rather than `session.get`: the rows were removed by the
        # database, not by the ORM, so the session identity map still holds them and
        # `get` would answer from memory that they are alive.
        remaining = (
            await db.execute(
                select(func.count())
                .select_from(Enrollment)
                .where(Enrollment.id.in_(enrollment_ids))
            )
        ).scalar_one()
        assert remaining == 0

        entry = (
            await db.execute(
                select(AuditLog).where(
                    AuditLog.subject == f"course:{course_id}",
                    AuditLog.action == "course_deleted",
                )
            )
        ).scalar_one()
        assert entry.actor_id == admin.id
        assert entry.detail == {
            "title": "Curso con gente dentro",
            "status": "published",
            "enrollment_count": 2,
            "completed_enrollment_count": 1,
        }

        await db.delete(entry)
        for learner in learners:
            await db.delete(await db.get(User, learner.id))
        await db.delete(admin)
        await db.delete(org)
        await db.commit()
