"""An archived course cannot be opened by a learner who still has the link.

Archiving means "stop showing this course to the learners", and yesterday only half of
that shipped: ``GET /enrollments`` stopped listing the course (see
``tests/test_course_archive.py``) while every route that *serves* it kept answering,
because they check the **enrollment** and archiving deliberately leaves enrollments
alone. So the course vanished from "Mis cursos" and stayed one saved URL away — hiding it
was a suggestion rather than a rule.

The gate is ``src/services/course_access.assert_learner_can_open``, and it is one
function on purpose: the same rule was already written out four times (v1 course detail,
v1 progress, ``POST /lessons/{id}/complete``, and ``routes/nodes._assert_course_open``),
which is how the fifth route would have been written without it.

What is asserted here:

* the gate's own truth table, including the admin exemption — ``POST /enrollments`` is
  admin-only and the course library uses it to self-enrol for "Probar curso", so the
  reviewer of an archived course *has* an enrollment row and only the role tells them
  apart from a learner;
* the two v1 learner routes and ``POST /lessons/{id}/complete`` through their route
  functions;
* the RAG scoping, so the tutor stops answering out of an archived course's documents;
* the tutor's on-screen-lesson context, which reads the served render from the database
  and therefore had to lose it too.

The v2 (node) surface is covered in ``tests/test_node_routes_authorization.py``, next to
the enrollment half of the same gate and its per-route list.

No database and no network: the repositories are in-memory doubles and the route
functions are called directly, the way ``tests/test_course_archive.py`` does.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from src.core.exceptions import ForbiddenError
from src.models import ContentStatus, EnrollmentStatus, UserRole
from src.routes import courses as courses_routes
from src.routes import lessons as lessons_routes
from src.services import retrieval
from src.services.chat_service import ChatService
from src.services.course_access import (
    ARCHIVED_MESSAGE,
    NOT_ENROLLED_MESSAGE,
    assert_learner_can_open,
)

NOW = datetime(2026, 8, 27, 9, 0, tzinfo=timezone.utc)

ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
LEARNER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
COURSE_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
NODE_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
LESSON_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")


# --------------------------------------------------------------------------------------
# Doubles
# --------------------------------------------------------------------------------------
@dataclass
class FakeUser:
    id: uuid.UUID = LEARNER_ID
    org_id: uuid.UUID = ORG_ID
    role: UserRole = UserRole.EMPLOYEE


@dataclass
class FakeCourse:
    """Enough of a ``Course`` row for the gate and the v1 read projections."""

    id: uuid.UUID = COURSE_ID
    org_id: uuid.UUID = ORG_ID
    status: ContentStatus = ContentStatus.PUBLISHED
    title: str = "Como aprende tu cerebro"
    description: str | None = None
    outcome: str | None = None
    delivery_mode: str = "static"
    schema_status: Any = None
    source_document_id: uuid.UUID | None = None
    folder_id: uuid.UUID | None = None
    created_at: datetime = NOW
    updated_at: datetime = NOW
    modules: list = field(default_factory=list)
    is_demo: bool = False


@dataclass
class FakeEnrollment:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    status: EnrollmentStatus = EnrollmentStatus.ASSIGNED
    started_at: Any = None
    completed_at: Any = None
    score: float | None = None


class FakeEnrollments:
    """The one method the gate needs, plus a record of whether it was asked."""

    def __init__(self, enrollment: FakeEnrollment | None) -> None:
        self.enrollment = enrollment
        self.asked: list[tuple[uuid.UUID, uuid.UUID]] = []

    async def get_by_user_and_course(
        self, user_id: uuid.UUID, course_id: uuid.UUID
    ) -> FakeEnrollment | None:
        self.asked.append((user_id, course_id))
        return self.enrollment


class StubDB:
    """Enough of ``AsyncSession`` for a route body that never reads or writes rows."""

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


def _archived() -> FakeCourse:
    return FakeCourse(status=ContentStatus.ARCHIVED)


# --------------------------------------------------------------------------------------
# The gate itself
# --------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_an_enrolled_learner_may_open_a_published_course() -> None:
    """The unchanged case, and the gate hands back the row it read."""
    row = FakeEnrollment()

    got = await assert_learner_can_open(
        user=FakeUser(), course=FakeCourse(), enrollments=FakeEnrollments(row)
    )

    assert got is row


@pytest.mark.asyncio
async def test_an_enrolled_learner_may_not_open_an_archived_course() -> None:
    """The hole: the enrollment survives archiving, so it cannot be the whole rule."""
    with pytest.raises(ForbiddenError) as raised:
        await assert_learner_can_open(
            user=FakeUser(),
            course=_archived(),
            enrollments=FakeEnrollments(FakeEnrollment()),
        )

    assert raised.value.status_code == 403
    assert raised.value.message == ARCHIVED_MESSAGE


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [ContentStatus.PUBLISHED, ContentStatus.ARCHIVED])
async def test_an_unenrolled_learner_is_told_only_that_much(
    status: ContentStatus,
) -> None:
    """Enrollment is checked first, so nobody's existing answer changed.

    The archive check only ever adds a denial for someone who *is* enrolled.
    """
    with pytest.raises(ForbiddenError) as raised:
        await assert_learner_can_open(
            user=FakeUser(),
            course=FakeCourse(status=status),
            enrollments=FakeEnrollments(None),
        )

    assert raised.value.message == NOT_ENROLLED_MESSAGE


@pytest.mark.asyncio
async def test_an_admin_may_open_an_archived_course_with_no_enrollment() -> None:
    """"Probar curso" is a creator tool: reviewing an archived course is the point."""
    got = await assert_learner_can_open(
        user=FakeUser(role=UserRole.ADMIN),
        course=_archived(),
        enrollments=FakeEnrollments(None),
    )

    assert got is None


@pytest.mark.asyncio
async def test_an_admin_who_self_enrolled_still_gets_their_row() -> None:
    """The self-enrolment of the course library is why the exemption is by **role**.

    The admin has an enrollment row exactly like a learner's, so the row cannot tell the
    two apart — and a caller that needs it (``POST /lessons/{id}/complete`` writes to it)
    must still receive it.
    """
    row = FakeEnrollment()

    got = await assert_learner_can_open(
        user=FakeUser(role=UserRole.ADMIN),
        course=_archived(),
        enrollments=FakeEnrollments(row),
    )

    assert got is row


# --------------------------------------------------------------------------------------
# GET /courses/{id} and GET /courses/{id}/progress
# --------------------------------------------------------------------------------------
def _install_course_routes(
    monkeypatch: pytest.MonkeyPatch,
    course: FakeCourse,
    enrollment: FakeEnrollment | None,
) -> None:
    class FakeCourseRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_detail(self, course_id: uuid.UUID, org_id: uuid.UUID):
            if course_id != course.id or org_id != course.org_id:
                return None
            return course

        async def list_artifact_generator_ids(self, _course_id: uuid.UUID) -> list:
            return []

    class FakeNodeRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def list_for_course(self, _course_id: uuid.UUID) -> list:
            return []

    monkeypatch.setattr(courses_routes, "CourseRepository", FakeCourseRepo)
    monkeypatch.setattr(courses_routes, "CourseNodeRepository", FakeNodeRepo)
    monkeypatch.setattr(
        courses_routes,
        "EnrollmentRepository",
        lambda _db: FakeEnrollments(enrollment),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route",
    [courses_routes.get_course, courses_routes.get_course_progress],
    ids=["detail", "progress"],
)
async def test_the_v1_learner_routes_refuse_an_archived_course(
    monkeypatch: pytest.MonkeyPatch, route: Any
) -> None:
    """The saved link, on both routes the course screen opens with."""
    _install_course_routes(monkeypatch, _archived(), FakeEnrollment())

    with pytest.raises(ForbiddenError) as raised:
        await route(user=FakeUser(), db=StubDB(), course_id=COURSE_ID)

    assert raised.value.status_code == 403
    assert raised.value.message == ARCHIVED_MESSAGE


@pytest.mark.asyncio
async def test_a_published_course_still_opens_for_its_learner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_course_routes(monkeypatch, FakeCourse(), FakeEnrollment())

    detail = await courses_routes.get_course(
        user=FakeUser(), db=StubDB(), course_id=COURSE_ID
    )
    progress = await courses_routes.get_course_progress(
        user=FakeUser(), db=StubDB(), course_id=COURSE_ID
    )

    assert detail.id == COURSE_ID
    assert detail.status == ContentStatus.PUBLISHED.value
    assert progress["total_lessons"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route",
    [courses_routes.get_course, courses_routes.get_course_progress],
    ids=["detail", "progress"],
)
async def test_an_admin_can_still_review_an_archived_course(
    monkeypatch: pytest.MonkeyPatch, route: Any
) -> None:
    """No enrollment at all, an archived course, and both routes answer.

    This is the flow that stopped anybody from writing this gate yesterday.
    """
    _install_course_routes(monkeypatch, _archived(), None)

    assert await route(user=FakeUser(role=UserRole.ADMIN), db=StubDB(), course_id=COURSE_ID)


# --------------------------------------------------------------------------------------
# POST /lessons/{id}/complete
# --------------------------------------------------------------------------------------
@dataclass
class FakeLesson:
    id: uuid.UUID = LESSON_ID
    exercises: list = field(default_factory=list)
    module: Any = None


def _install_lesson_route(
    monkeypatch: pytest.MonkeyPatch,
    course: FakeCourse,
    enrollment: FakeEnrollment | None,
) -> None:
    lesson = FakeLesson()
    lesson.module = type("FakeModule", (), {"course": course})()

    class FakeLessonRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_with_course_and_exercises(self, lesson_id: uuid.UUID):
            return lesson if lesson_id == lesson.id else None

    class FakeCourseRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_detail(self, _course_id: uuid.UUID, _org_id: uuid.UUID):
            # No ordered tree: the sequential-progression check skips itself, which is
            # not what this test is about.
            return None

    class FakeProgressRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_by_user_and_lesson(self, _user_id: uuid.UUID, _lesson_id: uuid.UUID):
            return None

        async def create(self, **_kwargs: Any) -> None:
            return None

    class FakeExerciseRepo:
        def __init__(self, _db: Any) -> None:
            pass

    class FakeEnrollmentService:
        def __init__(self, *_args: Any) -> None:
            pass

        async def compute_progress(self, **_kwargs: Any) -> float:
            return 0.5

    monkeypatch.setattr(lessons_routes, "LessonRepository", FakeLessonRepo)
    monkeypatch.setattr(lessons_routes, "CourseRepository", FakeCourseRepo)
    monkeypatch.setattr(lessons_routes, "LessonProgressRepository", FakeProgressRepo)
    monkeypatch.setattr(lessons_routes, "ExerciseRepository", FakeExerciseRepo)
    monkeypatch.setattr(lessons_routes, "EnrollmentService", FakeEnrollmentService)
    monkeypatch.setattr(
        lessons_routes,
        "EnrollmentRepository",
        lambda _db: FakeEnrollments(enrollment),
    )


@pytest.mark.asyncio
async def test_completing_a_lesson_of_an_archived_course_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Progress is a way of opening the course too: the write must go as well.

    Archiving no longer touches anybody's progress, so a learner who kept the lesson URL
    would otherwise have gone on advancing through a course nobody can see.
    """
    enrollment = FakeEnrollment()
    _install_lesson_route(monkeypatch, _archived(), enrollment)

    with pytest.raises(ForbiddenError) as raised:
        await lessons_routes.complete_lesson(
            user=FakeUser(), db=StubDB(), lesson_id=LESSON_ID
        )

    assert raised.value.message == ARCHIVED_MESSAGE
    # And nothing was written on the way out.
    assert enrollment.status == EnrollmentStatus.ASSIGNED
    assert enrollment.started_at is None


@pytest.mark.asyncio
async def test_completing_a_lesson_of_a_published_course_still_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enrollment = FakeEnrollment()
    _install_lesson_route(monkeypatch, FakeCourse(), enrollment)

    result = await lessons_routes.complete_lesson(
        user=FakeUser(), db=StubDB(), lesson_id=LESSON_ID
    )

    assert result == {"completed": True, "progress": 0.5}
    assert enrollment.status == EnrollmentStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_an_admin_with_no_enrollment_still_cannot_complete_a_lesson(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exemption is from the gate, not from needing a row.

    This route writes the enrollment's status, so there is nothing to do without one —
    exactly the answer this route gave before the gate existed.
    """
    _install_lesson_route(monkeypatch, FakeCourse(), None)

    with pytest.raises(ForbiddenError) as raised:
        await lessons_routes.complete_lesson(
            user=FakeUser(role=UserRole.ADMIN), db=StubDB(), lesson_id=LESSON_ID
        )

    assert raised.value.message == NOT_ENROLLED_MESSAGE


# --------------------------------------------------------------------------------------
# The RAG corpus (rung 2 of the grounding ladder)
# --------------------------------------------------------------------------------------
class CapturingSession:
    """Records the statement instead of running it, and answers with no rows."""

    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> Any:
        self.statements.append(statement)

        class _Result:
            def all(self) -> list:
                return []

        return _Result()


@pytest.mark.asyncio
async def test_an_archived_courses_documents_leave_the_tutors_corpus() -> None:
    """``enrolled_documents`` scopes by enrollment, and the enrollment outlives the
    archive — so without its own predicate the tutor would keep answering out of the
    material of a course the learner can no longer open."""
    db = CapturingSession()

    assert await retrieval.enrolled_documents(db, user_id=LEARNER_ID, org_id=ORG_ID) == []

    sql = str(
        db.statements[0].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "'archived'" in sql
    assert "courses.status !=" in sql


# --------------------------------------------------------------------------------------
# The tutor's on-screen-lesson context
# --------------------------------------------------------------------------------------
@dataclass
class FakeNode:
    id: uuid.UUID = NODE_ID
    org_id: uuid.UUID = ORG_ID
    course_id: uuid.UUID = COURSE_ID
    title: str = "Consolidacion durante el sueno"
    summary: str = "Dormir es parte del estudio."
    outcome: str | None = None
    position: int = 1
    archived: bool = False


def _install_chat_repos(monkeypatch: pytest.MonkeyPatch, course: FakeCourse) -> None:
    """``_node_context_block`` imports these inside the function, so the patch has to
    land on the repository modules rather than on ``chat_service``."""

    class FakeNodeRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_scoped(self, node_id: uuid.UUID, org_id: uuid.UUID):
            node = FakeNode()
            return node if node_id == node.id and org_id == node.org_id else None

        async def list_for_course(self, _course_id: uuid.UUID, include_archived: bool = False):
            return [FakeNode()]

    class FakeCourseRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_scoped(self, course_id: uuid.UUID, org_id: uuid.UUID):
            if course_id != course.id or org_id != course.org_id:
                return None
            return course

    monkeypatch.setattr(
        "src.repositories.course_node_repo.CourseNodeRepository", FakeNodeRepo
    )
    monkeypatch.setattr("src.repositories.course_repo.CourseRepository", FakeCourseRepo)


@pytest.mark.asyncio
async def test_the_tutor_loses_the_lesson_of_an_archived_course(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The context block reads the *served render* out of the database.

    Refusing the node route while the tutor still pastes the same lesson into the prompt
    would leave the material one question away.
    """
    _install_chat_repos(monkeypatch, _archived())
    service = ChatService(StubDB())

    block = await service._node_context_block(FakeUser(), {"node_id": str(NODE_ID)})

    assert block == ""


@pytest.mark.asyncio
async def test_the_tutor_keeps_the_lesson_of_a_published_course(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_chat_repos(monkeypatch, FakeCourse())
    service = ChatService(StubDB())

    block = await service._node_context_block(FakeUser(), {"node_id": str(NODE_ID)})

    assert "Como aprende tu cerebro" in block
    assert "Consolidacion durante el sueno" in block


@pytest.mark.asyncio
async def test_an_admin_previewing_keeps_the_lesson_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same reason as the routes: the reviewer of an archived course needs its tutor."""
    _install_chat_repos(monkeypatch, _archived())
    service = ChatService(StubDB())

    block = await service._node_context_block(
        FakeUser(role=UserRole.ADMIN), {"node_id": str(NODE_ID)}
    )

    assert "Como aprende tu cerebro" in block
