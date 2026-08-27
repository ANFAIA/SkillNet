"""Assigning a whole folder from the person's side: ``POST /enrollments``.

The library already had folder -> people (``POST /course-folders/{id}/assign``). The
employee record had only course -> one person, so a new hire needed one click per course
of an onboarding folder. This file pins the other direction on the endpoint that record
already talks to, and the four properties that make it safe to use:

* ``folder_id`` enrolls **every published** course of the folder — the same set the
  library endpoint enrolls, because both read ``list_published_course_ids``. A draft in
  the folder is not assigned and is not counted.
* Exactly one target: ``course_id`` **or** ``folder_id``, never both and never neither.
* A folder of another organisation is a 404, not a 403 and not an assignment.
* Re-assigning is idempotent: the rows that already existed are reported as skipped, not
  raised as a conflict, so "assign the onboarding folder" is safe to press twice.

No database and no network: the repositories the route names are replaced with in-memory
doubles and the session dependency is a stub. ``EnrollmentService`` itself is the real
one — the idempotency asserted here is its own, not a double's.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.deps.auth import current_user
from src.deps.db import get_async_session
from src.main import create_app
from src.models import EnrollmentStatus, UserRole
from src.routes import enrollments as enrollments_routes

PREFIX = "/api/v1"

ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
OTHER_ORG_ID = uuid.UUID("1111ffff-1111-1111-1111-111111111111")
ADMIN_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
LEARNER_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
FOLDER_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
PUBLISHED_A = uuid.UUID("55555555-5555-5555-5555-555555555555")
PUBLISHED_B = uuid.UUID("66666666-6666-6666-6666-666666666666")
DRAFT_C = uuid.UUID("77777777-7777-7777-7777-777777777777")


# --------------------------------------------------------------------------------------
# Doubles
# --------------------------------------------------------------------------------------
@dataclass
class FakeUser:
    id: uuid.UUID = ADMIN_ID
    org_id: uuid.UUID = ORG_ID
    role: UserRole = UserRole.ADMIN


@dataclass
class FakeCourse:
    id: uuid.UUID
    title: str
    org_id: uuid.UUID = ORG_ID
    #: `_read` runs the real `resolve_delivery`, which reads both of these.
    delivery_mode: str = "static"
    schema_status: str = "none"


@dataclass
class FakeEnrollment:
    id: uuid.UUID
    user_id: uuid.UUID
    course_id: uuid.UUID
    course: FakeCourse
    status: EnrollmentStatus = EnrollmentStatus.ASSIGNED
    deadline: Any = None
    score: float | None = None
    started_at: Any = None
    completed_at: Any = None


class FakeResult:
    """Just enough of a SQLAlchemy ``Result`` for the two reads that reach a session."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return list(self._rows)

    def scalar_one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None


@dataclass
class World:
    """The data the doubles answer with, mutated per test."""

    #: Courses in the folder, in library order. Only the published ones are assignable.
    folder_courses: dict[uuid.UUID, FakeCourse] = field(default_factory=dict)
    published_ids: list[uuid.UUID] = field(default_factory=list)
    folder_org_id: uuid.UUID = ORG_ID
    #: Learners of `org_id`, as `_assert_users_in_org` would find them.
    users_in_org: list[uuid.UUID] = field(default_factory=lambda: [LEARNER_ID])
    #: `(user_id, course_id)` pairs already enrolled before the request.
    existing: set[tuple[uuid.UUID, uuid.UUID]] = field(default_factory=set)
    created: list[FakeEnrollment] = field(default_factory=list)
    committed: bool = False


class StubSession:
    """The route's own session. Only the workspace-mode probe reads it."""

    def __init__(self, world: World) -> None:
        self.world = world

    async def execute(self, _query: Any) -> FakeResult:
        # `require_organization_workspace` reads `workspace_mode`; no row means "not
        # individual", which is the organisation path these routes need.
        return FakeResult([])

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.world.committed = True

    async def rollback(self) -> None:
        return None


def _install(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    """Replace the repositories ``src/routes/enrollments.py`` names with doubles."""

    class NoopSavepoint:
        """``session.begin_nested()``: the SAVEPOINT ``_enrol_once`` inserts inside."""

        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *_exc: Any) -> bool:
            return False

    class UserSession:
        """The session ``EnrollmentService`` reaches through its enrollment repo."""

        async def execute(self, _query: Any) -> FakeResult:
            # `_assert_users_in_org` reads `[(id,), ...]`.
            return FakeResult([(uid,) for uid in world.users_in_org])

        def begin_nested(self) -> Any:
            return NoopSavepoint()

        async def flush(self) -> None:
            return None

    class FakeEnrollmentRepo:
        def __init__(self, _db: Any) -> None:
            self.session = UserSession()

        async def get_by_user_and_course(
            self, user_id: uuid.UUID, course_id: uuid.UUID
        ) -> Any:
            if (user_id, course_id) in world.existing:
                return object()
            return None

        async def create(self, **kwargs: Any) -> FakeEnrollment:
            enrollment = FakeEnrollment(
                id=uuid.uuid4(),
                user_id=kwargs["user_id"],
                course_id=kwargs["course_id"],
                course=world.folder_courses[kwargs["course_id"]],
                deadline=kwargs.get("deadline"),
            )
            world.created.append(enrollment)
            world.existing.add((enrollment.user_id, enrollment.course_id))
            return enrollment

        async def get_with_course(self, enrollment_id: uuid.UUID) -> Any:
            for enrollment in world.created:
                if enrollment.id == enrollment_id:
                    return enrollment
            return None

        async def existing_pairs(
            self, course_ids: Any, user_ids: Any
        ) -> set[tuple[uuid.UUID, uuid.UUID]]:
            """The batch snapshot `assign_courses` takes before its loop."""
            wanted_courses, wanted_users = set(course_ids), set(user_ids)
            return {
                pair
                for pair in world.existing
                if pair[0] in wanted_users and pair[1] in wanted_courses
            }

        async def list_with_courses(self, ids: Any) -> list[FakeEnrollment]:
            """The batch reload the assignment answer echoes with."""
            wanted = set(ids)
            return [row for row in world.created if row.id in wanted]

    class FakeCourseRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_scoped(self, course_id: uuid.UUID, org_id: uuid.UUID) -> Any:
            course = world.folder_courses.get(course_id)
            if course is None or course.org_id != org_id:
                return None
            return course

    class FakeFolderRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_scoped(self, folder_id: uuid.UUID, org_id: uuid.UUID) -> Any:
            if folder_id != FOLDER_ID or world.folder_org_id != org_id:
                return None
            return object()

        async def list_published_course_ids(
            self, folder_id: uuid.UUID, org_id: uuid.UUID
        ) -> list[uuid.UUID]:
            if folder_id != FOLDER_ID or world.folder_org_id != org_id:
                return []
            return list(world.published_ids)

    class FakeExerciseRepo:
        def __init__(self, _db: Any) -> None:
            pass

    class FakeUserGroupRepo:
        """No groups exist in this file's world; every order names people directly."""

        def __init__(self, _session: Any) -> None:
            pass

        async def scoped_ids(self, group_ids: Any, _org_id: uuid.UUID) -> set:
            return set()

        async def memberships(
            self, group_ids: Any, _org_id: uuid.UUID
        ) -> list[tuple[uuid.UUID, uuid.UUID, bool]]:
            return []

    class FakeLessonProgressRepo:
        def __init__(self, _session: Any) -> None:
            pass

    monkeypatch.setattr(enrollments_routes, "EnrollmentRepository", FakeEnrollmentRepo)
    monkeypatch.setattr(enrollments_routes, "CourseRepository", FakeCourseRepo)
    monkeypatch.setattr(enrollments_routes, "ExerciseRepository", FakeExerciseRepo)
    monkeypatch.setattr(
        enrollments_routes, "CourseFolderRepository", FakeFolderRepo
    )
    # `EnrollmentService.__init__` builds this one itself when it is not passed in.
    monkeypatch.setattr(
        "src.services.enrollment_service.LessonProgressRepository",
        FakeLessonProgressRepo,
    )
    monkeypatch.setattr(
        "src.services.enrollment_service.UserGroupRepository", FakeUserGroupRepo
    )


@pytest.fixture
def world() -> World:
    courses = {
        PUBLISHED_A: FakeCourse(id=PUBLISHED_A, title="Bienvenida"),
        PUBLISHED_B: FakeCourse(id=PUBLISHED_B, title="Seguridad"),
        DRAFT_C: FakeCourse(id=DRAFT_C, title="Borrador"),
    }
    return World(
        folder_courses=courses, published_ids=[PUBLISHED_A, PUBLISHED_B]
    )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, world: World) -> TestClient:
    _install(monkeypatch, world)
    app = create_app()
    app.dependency_overrides[get_async_session] = lambda: StubSession(world)
    app.dependency_overrides[current_user] = lambda: FakeUser()
    return TestClient(app, raise_server_exceptions=False)


def _assign(client: TestClient, **body: Any):
    return client.post(f"{PREFIX}/enrollments", json={"user_ids": [str(LEARNER_ID)], **body})


# --------------------------------------------------------------------------------------
# The folder branch
# --------------------------------------------------------------------------------------
def test_a_folder_enrolls_every_published_course_and_no_draft(
    client: TestClient, world: World
) -> None:
    response = _assign(client, folder_id=str(FOLDER_ID), deadline="2026-12-31")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["course_count"] == 2
    assert body["created_count"] == 2
    assert body["skipped_existing_count"] == 0
    assert {row["course_id"] for row in body["enrollments"]} == {
        str(PUBLISHED_A),
        str(PUBLISHED_B),
    }
    # The draft in the same folder was never touched.
    assert DRAFT_C not in {enrollment.course_id for enrollment in world.created}
    # And the deadline of the order reached every row.
    assert {str(enrollment.deadline) for enrollment in world.created} == {"2026-12-31"}
    assert world.committed


def test_reassigning_the_same_folder_creates_nothing_and_reports_the_skips(
    client: TestClient, world: World
) -> None:
    """The reason a "assign the onboarding folder" button is safe to press twice."""
    first = _assign(client, folder_id=str(FOLDER_ID))
    assert first.status_code == 201, first.text

    second = _assign(client, folder_id=str(FOLDER_ID))

    assert second.status_code == 201, second.text
    body = second.json()
    assert body["course_count"] == 2
    assert body["created_count"] == 0
    assert body["skipped_existing_count"] == 2
    assert body["enrollments"] == []


def test_a_folder_with_nothing_published_is_an_honest_zero(
    client: TestClient, world: World
) -> None:
    """Not an error, and not a lie either: the caller is told nobody was enrolled."""
    world.published_ids = []

    response = _assign(client, folder_id=str(FOLDER_ID))

    assert response.status_code == 201, response.text
    assert response.json() == {
        "course_count": 0,
        "created_count": 0,
        "skipped_existing_count": 0,
        # One person was named and resolved; there was simply nothing to give them.
        "person_count": 1,
        "skipped_inactive_count": 0,
        "enrollments": [],
        "enrollments_truncated": False,
    }
    assert world.created == []


def test_a_folder_of_another_organisation_is_a_404(
    client: TestClient, world: World
) -> None:
    world.folder_org_id = OTHER_ORG_ID

    response = _assign(client, folder_id=str(FOLDER_ID))

    assert response.status_code == 404, response.text
    assert response.json()["code"] == "NOT_FOUND"
    assert world.created == []


def test_a_learner_of_another_organisation_is_refused_before_any_write(
    client: TestClient, world: World
) -> None:
    """``_assert_users_in_org`` runs on this branch too, and it runs first."""
    world.users_in_org = []

    response = _assign(client, folder_id=str(FOLDER_ID))

    assert response.status_code == 403, response.text
    assert world.created == []


# --------------------------------------------------------------------------------------
# Exactly one target
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {"course_id": str(PUBLISHED_A), "folder_id": str(FOLDER_ID)}, id="both"
        ),
        pytest.param({}, id="neither"),
    ],
)
def test_an_order_names_exactly_one_target(
    client: TestClient, world: World, body: dict
) -> None:
    response = _assign(client, **body)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert world.created == []


# --------------------------------------------------------------------------------------
# The old contract, unchanged
# --------------------------------------------------------------------------------------
def test_a_single_course_still_answers_with_a_bare_list(
    client: TestClient, world: World
) -> None:
    """Three screens send this shape and none of them were changed."""
    response = _assign(client, course_id=str(PUBLISHED_A))

    assert response.status_code == 201, response.text
    body = response.json()
    assert isinstance(body, list)
    assert [row["course_id"] for row in body] == [str(PUBLISHED_A)]
    assert body[0]["course_title"] == "Bienvenida"
    assert body[0]["delivery_mode"] == "static"
