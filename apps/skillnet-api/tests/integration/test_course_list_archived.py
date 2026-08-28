"""``GET /courses`` and the archived rows: opt-out, not a changed default.

Archiving a course hides it from the learners, and until the library asked for it the
admin still saw it in "All" — so archiving to tidy the catalogue left the catalogue
exactly as full as before. The library now asks for the archived courses to be left out
and offers them behind their own entry, the way a chat app does.

The flag is an opt-out because ``GET /courses`` has other callers (the demo lookup, the
folder counts) that mean the whole catalogue when they ask for no status. What has to be
proved against a real database is that the three answers stay distinct: the default still
returns everything, ``include_archived=false`` drops the archived rows from both the page
and the ``total``, and asking for ``status=archived`` still returns them regardless.
"""

from __future__ import annotations

import uuid

import pytest

from src.deps.db import async_session_factory
from src.models import ContentStatus, Course, Organization, User, UserRole
from src.repositories.course_repo import CourseRepository

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_archived_courses_are_hidden_only_when_asked() -> None:
    suffix = uuid.uuid4().hex[:8]
    async with async_session_factory() as db:
        org = Organization(name=f"Arch {suffix}", slug=f"arch-{suffix}", settings={})
        db.add(org)
        await db.flush()
        admin = User(
            org_id=org.id,
            email=f"admin-{suffix}@archived.example",
            hashed_password="x",
            full_name="Admin",
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(admin)
        await db.flush()

        live = Course(
            org_id=org.id,
            title=f"Vigente {suffix}",
            created_by=admin.id,
            status=ContentStatus.PUBLISHED,
        )
        gone = Course(
            org_id=org.id,
            title=f"Retirado {suffix}",
            created_by=admin.id,
            status=ContentStatus.ARCHIVED,
        )
        db.add_all([live, gone])
        await db.commit()

        repo = CourseRepository(db)

        rows, total = await repo.list_courses(org_id=org.id)
        assert total == 2
        assert {course.id for course, _, _ in rows} == {live.id, gone.id}

        rows, total = await repo.list_courses(org_id=org.id, include_archived=False)
        assert total == 1
        assert [course.id for course, _, _ in rows] == [live.id]

        # An explicit status is the caller saying which rows it wants; the flag must not
        # turn `status=archived` into a question with no possible answer.
        rows, total = await repo.list_courses(
            org_id=org.id,
            status=ContentStatus.ARCHIVED,
            include_archived=False,
        )
        assert total == 1
        assert [course.id for course, _, _ in rows] == [gone.id]

        await db.delete(await db.get(Course, live.id))
        await db.delete(await db.get(Course, gone.id))
        await db.delete(admin)
        await db.delete(org)
        await db.commit()
