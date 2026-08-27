"""Moving a course into a folder works on the FIRST attempt (needs PostgreSQL).

Two bugs met in `PUT /courses/{id}` and only a real database could see either.

1. `TimestampMixin.updated_at` used to declare `onupdate=text("now()")`. A SQL expression
   is computed by the server, so SQLAlchemy cannot know the new value: it registers the
   column as *postfetch* for the UPDATE and expires the attribute. `deps/db.py` sets
   `expire_on_commit=False`, which does not undo that expiration, so the projector's
   plain `course.updated_at` — a synchronous read, after `await db.commit()` — triggered
   an implicit refresh outside SQLAlchemy's greenlet: `MissingGreenlet`, delivered to the
   SPA as a bare `text/plain` 500 and shown as "Unknown error". Retrying "worked" only
   because the first attempt had already committed, so the second UPDATE was a no-op with
   nothing to postfetch. That is why this test moves the course **once**.
2. The projector fills `folder_name` from `course.folder`, and the write path reads the
   course through `get_scoped`, which did not load that relationship — so the response
   carried the right `folder_id` next to `folder_name: null`.

The route handler is called directly rather than over HTTP. Both failures live in the
handler's synchronous projection after the commit, not in the transport, and going
through `TestClient` would run the request in a second event loop while the fixtures own
connections from this one — the exact cross-loop hazard `conftest.py` documents. A
`CourseRead` coming back at all *is* the 200: FastAPI serializes it, and anything raised
here is what would otherwise have been the 500.
"""

from __future__ import annotations

import uuid

import pytest

from src.deps.db import async_session_factory
from src.models import Course, CourseFolder, Organization, User, UserRole
from src.models.course import ContentStatus
from src.routes.courses import update_course
from src.schemas.course import CourseUpdate

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_moving_a_course_into_a_folder_succeeds_on_the_first_attempt() -> None:
    suffix = uuid.uuid4().hex[:8]
    async with async_session_factory() as db:
        org = Organization(name=f"Org {suffix}", slug=f"org-{suffix}", settings={})
        db.add(org)
        await db.flush()

        admin = User(
            org_id=org.id,
            email=f"admin-{suffix}@folders.example",
            hashed_password="x",
            full_name="Admin",
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(admin)
        await db.flush()

        folder = CourseFolder(org_id=org.id, name=f"Soporte {suffix}")
        course = Course(
            org_id=org.id,
            title="Recuperar entradas",
            created_by=admin.id,
            status=ContentStatus.DRAFT,
        )
        db.add_all([folder, course])
        await db.commit()

        # The one call under test. Once, never twice.
        result = await update_course(
            admin=admin,
            db=db,
            course_id=course.id,
            body=CourseUpdate(folder_id=folder.id),
        )

        assert result.id == course.id
        assert result.folder_id == folder.id
        # The projection the admin library reads; `null` here was the second bug.
        assert result.folder_name == folder.name
        # Read again after the commit: this is the attribute that used to be expired.
        # Reading it at all is the assertion — an expired attribute raises here.
        assert result.updated_at is not None
        assert course.updated_at is not None
        assert course.updated_at >= course.created_at.replace(tzinfo=None)

        # And it persisted, from a session that never saw the write.
        async with async_session_factory() as verify:
            reloaded = await verify.get(Course, course.id)
            assert reloaded is not None
            assert reloaded.folder_id == folder.id

        # Cleanup.
        await db.delete(course)
        await db.delete(folder)
        await db.delete(admin)
        await db.delete(org)
        await db.commit()


@pytest.mark.asyncio
async def test_unfiling_a_course_clears_both_the_id_and_the_name() -> None:
    """`folder_id: null` is a legal move, and the name must follow the id out."""
    suffix = uuid.uuid4().hex[:8]
    async with async_session_factory() as db:
        org = Organization(name=f"Org {suffix}", slug=f"org-{suffix}", settings={})
        db.add(org)
        await db.flush()

        admin = User(
            org_id=org.id,
            email=f"admin-{suffix}@folders.example",
            hashed_password="x",
            full_name="Admin",
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(admin)
        await db.flush()

        folder = CourseFolder(org_id=org.id, name=f"Archivo {suffix}")
        db.add(folder)
        await db.flush()
        course = Course(
            org_id=org.id,
            title="Alergenos",
            created_by=admin.id,
            status=ContentStatus.DRAFT,
            folder_id=folder.id,
        )
        db.add(course)
        await db.commit()

        result = await update_course(
            admin=admin,
            db=db,
            course_id=course.id,
            body=CourseUpdate(folder_id=None),
        )

        assert result.folder_id is None
        # The stale relationship used to survive the column change and keep reporting
        # the old folder's name next to a null id.
        assert result.folder_name is None

        await db.delete(course)
        await db.delete(folder)
        await db.delete(admin)
        await db.delete(org)
        await db.commit()
