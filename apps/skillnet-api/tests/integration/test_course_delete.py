"""Deleting a draft course against a real schema: the case that used to answer 500.

Every course produced by a generation run has a ``generation_jobs`` row pointing at it,
and until migration 0024 that foreign key had no ``ON DELETE``. ``DELETE /courses/{id}``
therefore raised ``ForeignKeyViolation`` for exactly the courses an admin most wants to
remove — the drafts a failed run left behind. Only a real database can prove the
constraint now behaves: the unit suite in ``tests/test_course_delete.py`` covers the rules
and the file cleanup, this covers the schema.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from src.core.exceptions import ConflictError
from src.deps.db import async_session_factory
from src.models import (
    ChatSession,
    ContentStatus,
    Course,
    Enrollment,
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
async def test_a_draft_with_an_enrollment_is_refused_not_deleted() -> None:
    suffix = uuid.uuid4().hex[:8]
    async with async_session_factory() as db:
        org, admin = await _world(db, suffix)
        learner = User(
            org_id=org.id,
            email=f"learner-{suffix}@delete.example",
            hashed_password="x",
            full_name="Learner",
            role=UserRole.EMPLOYEE,
            is_active=True,
        )
        db.add(learner)
        await db.flush()
        course = Course(
            org_id=org.id,
            title="Curso con gente dentro",
            created_by=admin.id,
            status=ContentStatus.DRAFT,
        )
        db.add(course)
        await db.flush()
        enrollment = Enrollment(
            user_id=learner.id, course_id=course.id, assigned_by=admin.id
        )
        db.add(enrollment)
        await db.commit()
        course_id = course.id

        with pytest.raises(ConflictError):
            await CourseService(CourseRepository(db)).delete(
                course_id=course_id, org_id=org.id
            )
        await db.rollback()

        assert await db.get(Course, course_id) is not None

        await db.delete(await db.get(Enrollment, enrollment.id))
        await db.delete(await db.get(Course, course_id))
        await db.delete(learner)
        await db.delete(admin)
        await db.delete(org)
        await db.commit()
