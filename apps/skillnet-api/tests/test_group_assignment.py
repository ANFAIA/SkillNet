"""Assigning training to a whole group, through the endpoints that already existed.

There is no new assignment endpoint. ``POST /enrollments`` and
``POST /course-folders/{id}/assign`` both learned one field, ``group_ids``, and both
resolve it through the *same* ``EnrollmentService.resolve_audience`` — the single place a
group ever becomes a list of people. This file pins what that means:

* a group expands, server-side, to its members; the client never sends them;
* people and groups **add up** (the target stays exclusive, the audience does not), and
  someone named twice is enrolled once;
* a **deactivated** member is not enrolled and is reported, while a person named
  explicitly is enrolled whatever their state — an instruction is not a query;
* an unknown or foreign group is a 404 that wrote nothing;
* a created row remembers the group that put it there (``source_group_id``), **per
  person**: not for somebody the caller also named by hand, and not for somebody who is
  in two of the named groups;
* the response *shape* changes with the request, and the old shape is exactly preserved:
  ``{course_id, user_ids}`` still answers a bare list;
* an order too large for one request is a 422 that says how large, not a timeout;
* the echoed rows are capped, and say so instead of looking like the whole set.

No database and no network: the repositories the routes name are replaced with in-memory
doubles. ``EnrollmentService`` is the real one, so the idempotency, the deduplication and
the audience rules asserted here are its own.
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
from src.routes import course_folders as folder_routes
from src.routes import enrollments as enrollments_routes
from src.services import enrollment_service as enrollment_service_module

PREFIX = "/api/v1"

ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
ADMIN_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
FOLDER_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
COURSE_A = uuid.UUID("44444444-4444-4444-4444-444444444444")
COURSE_B = uuid.UUID("55555555-5555-5555-5555-555555555555")

TARDE = uuid.UUID("66666666-6666-6666-6666-666666666666")
MANANA = uuid.UUID("77777777-7777-7777-7777-777777777777")
#: Exists, but in another organization. Must be indistinguishable from a missing one.
FOREIGN_GROUP = uuid.UUID("88888888-8888-8888-8888-888888888888")

ANA = uuid.UUID("a0000000-0000-4000-8000-000000000001")
BRUNO = uuid.UUID("a0000000-0000-4000-8000-000000000002")
CARLA = uuid.UUID("a0000000-0000-4000-8000-000000000003")
#: In `TARDE`, and deactivated.
DIEGO = uuid.UUID("a0000000-0000-4000-8000-000000000004")


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
    source_group_id: uuid.UUID | None = None
    status: EnrollmentStatus = EnrollmentStatus.ASSIGNED
    deadline: Any = None
    score: float | None = None
    started_at: Any = None
    completed_at: Any = None


@dataclass
class World:
    courses: dict[uuid.UUID, FakeCourse] = field(default_factory=dict)
    published_ids: list[uuid.UUID] = field(default_factory=list)
    #: Group -> its members, as membership rows would have them.
    memberships: dict[uuid.UUID, list[uuid.UUID]] = field(default_factory=dict)
    #: Everyone of `ORG_ID`, and whether their account is active.
    people: dict[uuid.UUID, bool] = field(default_factory=dict)
    existing: set[tuple[uuid.UUID, uuid.UUID]] = field(default_factory=set)
    created: list[FakeEnrollment] = field(default_factory=list)
    committed: bool = False
    #: Every `existing_pairs` call, to prove the batch read is one query and not N.
    pair_lookups: int = 0
    #: Every single-pair read, for the same reason from the other side.
    single_lookups: int = 0


class StubSession:
    """The route's own session. Only the workspace-mode probe reads it."""

    def __init__(self, world: World) -> None:
        self.world = world

    async def execute(self, _query: Any) -> Any:
        # No organization row means "not individual", the path these routes need.
        return _Rows([])

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.world.committed = True

    async def rollback(self) -> None:
        return None


class _Rows:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return list(self._rows)

    def scalar_one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None


def _install(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    class NoopSavepoint:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *_exc: Any) -> bool:
            return False

    class UserSession:
        async def execute(self, _query: Any) -> _Rows:
            # `_assert_users_in_org` reads `[(id,), ...]` for the people of the org.
            # Deactivated people are still people: this query has no `is_active` filter
            # in production either.
            return _Rows([(uid,) for uid in world.people])

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
            world.single_lookups += 1
            if (user_id, course_id) in world.existing:
                return next(
                    (
                        row
                        for row in world.created
                        if (row.user_id, row.course_id) == (user_id, course_id)
                    ),
                    FakeEnrollment(
                        id=uuid.uuid4(),
                        user_id=user_id,
                        course_id=course_id,
                        course=world.courses[course_id],
                    ),
                )
            return None

        async def existing_pairs(self, course_ids: Any, user_ids: Any) -> set:
            world.pair_lookups += 1
            wanted_courses, wanted_users = set(course_ids), set(user_ids)
            return {
                pair
                for pair in world.existing
                if pair[0] in wanted_users and pair[1] in wanted_courses
            }

        async def list_with_courses(self, ids: Any) -> list[FakeEnrollment]:
            wanted = set(ids)
            return [row for row in world.created if row.id in wanted]

        async def create(self, **kwargs: Any) -> FakeEnrollment:
            enrollment = FakeEnrollment(
                id=uuid.uuid4(),
                user_id=kwargs["user_id"],
                course_id=kwargs["course_id"],
                course=world.courses[kwargs["course_id"]],
                source_group_id=kwargs.get("source_group_id"),
                deadline=kwargs.get("deadline"),
            )
            world.created.append(enrollment)
            world.existing.add((enrollment.user_id, enrollment.course_id))
            return enrollment

        async def get_with_course(self, enrollment_id: uuid.UUID) -> Any:
            return next(
                (row for row in world.created if row.id == enrollment_id), None
            )

    class FakeCourseRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_scoped(self, course_id: uuid.UUID, org_id: uuid.UUID) -> Any:
            course = world.courses.get(course_id)
            return course if course and course.org_id == org_id else None

    class FakeFolderRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_scoped(self, folder_id: uuid.UUID, org_id: uuid.UUID) -> Any:
            return object() if folder_id == FOLDER_ID and org_id == ORG_ID else None

        async def list_published_course_ids(
            self, folder_id: uuid.UUID, org_id: uuid.UUID
        ) -> list[uuid.UUID]:
            if folder_id != FOLDER_ID or org_id != ORG_ID:
                return []
            return list(world.published_ids)

    class FakeExerciseRepo:
        def __init__(self, _db: Any) -> None:
            pass

    class FakeLessonProgressRepo:
        def __init__(self, _session: Any) -> None:
            pass

    class FakeUserGroupRepo:
        def __init__(self, _session: Any) -> None:
            pass

        async def scoped_ids(self, group_ids: Any, org_id: uuid.UUID) -> set:
            if org_id != ORG_ID:
                return set()
            return {gid for gid in group_ids if gid in world.memberships}

        async def memberships(
            self, group_ids: Any, org_id: uuid.UUID
        ) -> list[tuple[uuid.UUID, uuid.UUID, bool]]:
            """Raw `(group, user, is_active)` rows, exactly as the real query returns.

            Deliberately *not* deduplicated: somebody in two of the named groups shows up
            twice, which is what makes the ambiguity rule below testable at all.
            """
            rows: list[tuple[uuid.UUID, uuid.UUID, bool]] = []
            for gid in group_ids:
                for uid in world.memberships.get(gid, []):
                    if uid in world.people and org_id == ORG_ID:
                        rows.append((gid, uid, world.people[uid]))
            return rows

    monkeypatch.setattr(enrollments_routes, "EnrollmentRepository", FakeEnrollmentRepo)
    monkeypatch.setattr(enrollments_routes, "CourseRepository", FakeCourseRepo)
    monkeypatch.setattr(enrollments_routes, "ExerciseRepository", FakeExerciseRepo)
    monkeypatch.setattr(enrollments_routes, "CourseFolderRepository", FakeFolderRepo)
    monkeypatch.setattr(folder_routes, "EnrollmentRepository", FakeEnrollmentRepo)
    monkeypatch.setattr(folder_routes, "CourseRepository", FakeCourseRepo)
    monkeypatch.setattr(folder_routes, "ExerciseRepository", FakeExerciseRepo)
    monkeypatch.setattr(folder_routes, "CourseFolderRepository", FakeFolderRepo)
    monkeypatch.setattr(
        "src.services.enrollment_service.LessonProgressRepository",
        FakeLessonProgressRepo,
    )
    monkeypatch.setattr(
        "src.services.enrollment_service.UserGroupRepository", FakeUserGroupRepo
    )


@pytest.fixture
def world() -> World:
    return World(
        courses={
            COURSE_A: FakeCourse(id=COURSE_A, title="Bienvenida"),
            COURSE_B: FakeCourse(id=COURSE_B, title="Seguridad"),
        },
        published_ids=[COURSE_A, COURSE_B],
        memberships={TARDE: [ANA, BRUNO, DIEGO], MANANA: [BRUNO, CARLA]},
        people={ANA: True, BRUNO: True, CARLA: True, DIEGO: False},
    )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, world: World) -> TestClient:
    _install(monkeypatch, world)
    app = create_app()
    app.dependency_overrides[get_async_session] = lambda: StubSession(world)
    app.dependency_overrides[current_user] = lambda: FakeUser()
    return TestClient(app, raise_server_exceptions=False)


def _post(client: TestClient, **body: Any):
    return client.post(f"{PREFIX}/enrollments", json=body)


def _enrolled(world: World, course_id: uuid.UUID) -> set[uuid.UUID]:
    return {row.user_id for row in world.created if row.course_id == course_id}


# --------------------------------------------------------------------------------------
# Expansion
# --------------------------------------------------------------------------------------
def test_a_group_enrols_its_active_members(client: TestClient, world: World) -> None:
    response = _post(client, course_id=str(COURSE_A), group_ids=[str(TARDE)])

    assert response.status_code == 201, response.text
    body = response.json()
    # Ana and Bruno. Diego is a member and is deactivated.
    assert _enrolled(world, COURSE_A) == {ANA, BRUNO}
    assert body["created_count"] == 2
    assert body["person_count"] == 2
    assert body["skipped_inactive_count"] == 1
    assert world.committed


def test_the_client_never_sends_the_members(client: TestClient, world: World) -> None:
    """The request body carried one group id and no people. That is the whole point.

    With the people list paginated the browser does not know every member, and the
    100-``user_ids`` cap would stop it long before a real group ran out. Expansion has
    exactly one home, and this is the assertion that it is the server's.
    """
    response = _post(client, course_id=str(COURSE_A), group_ids=[str(TARDE)])

    assert response.status_code == 201
    assert len(_enrolled(world, COURSE_A)) == 2


def test_people_and_groups_add_up_without_duplicating_anyone(
    client: TestClient, world: World
) -> None:
    """Bruno is named *and* in both groups, and gets exactly one enrollment.

    The target is exclusive (a course or a folder, never both) because "both" has no
    obvious meaning. The audience is the opposite: "the afternoon shift plus Carla" is
    unambiguous, so the union is the answer — deduplicated, or the same person would go
    through the enrollment loop three times.
    """
    response = _post(
        client,
        course_id=str(COURSE_A),
        user_ids=[str(BRUNO)],
        group_ids=[str(TARDE), str(MANANA)],
    )

    assert response.status_code == 201, response.text
    assert _enrolled(world, COURSE_A) == {ANA, BRUNO, CARLA}
    assert len([row for row in world.created if row.user_id == BRUNO]) == 1
    assert response.json()["person_count"] == 3


def test_a_named_person_is_enrolled_even_when_deactivated(
    client: TestClient, world: World
) -> None:
    """Naming somebody is an instruction; resolving a group is a question.

    Diego is deactivated. Through ``TARDE`` he is skipped and counted. Named directly he
    is enrolled, because the admin said so and a silent refusal would be the surprise.
    """
    response = _post(client, course_id=str(COURSE_A), user_ids=[str(DIEGO)])

    assert response.status_code == 201, response.text
    assert _enrolled(world, COURSE_A) == {DIEGO}


def test_naming_a_deactivated_member_does_not_also_count_them_as_skipped(
    client: TestClient, world: World
) -> None:
    """Diego is deactivated *and* in TARDE *and* named. He is enrolled, once, and the
    "not enrolled because deactivated" count must not claim him."""
    body = _post(
        client,
        course_id=str(COURSE_A),
        user_ids=[str(DIEGO)],
        group_ids=[str(TARDE)],
    ).json()

    assert DIEGO in _enrolled(world, COURSE_A)
    assert body["skipped_inactive_count"] == 0
    assert body["person_count"] == 3  # Diego, Ana, Bruno


def test_an_empty_group_is_an_honest_zero(client: TestClient, world: World) -> None:
    """Not an error, and not something that looks like success either."""
    world.memberships[TARDE] = []

    response = _post(client, course_id=str(COURSE_A), group_ids=[str(TARDE)])

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["person_count"] == 0
    assert body["created_count"] == 0
    assert world.created == []


def test_a_group_of_only_deactivated_people_says_why_nobody_was_enrolled(
    client: TestClient, world: World
) -> None:
    world.memberships[TARDE] = [DIEGO]

    body = _post(client, course_id=str(COURSE_A), group_ids=[str(TARDE)]).json()

    assert body["created_count"] == 0
    assert body["person_count"] == 0
    # Without this the screen could only say "0 enrollments", which reads as a bug.
    assert body["skipped_inactive_count"] == 1


# --------------------------------------------------------------------------------------
# Tenant safety and bad input
# --------------------------------------------------------------------------------------
def test_an_unknown_group_is_a_404_that_wrote_nothing(
    client: TestClient, world: World
) -> None:
    response = _post(
        client, course_id=str(COURSE_A), group_ids=[str(TARDE), str(FOREIGN_GROUP)]
    )

    assert response.status_code == 404, response.text
    # And in particular the *valid* group in the same order did not half-assign.
    assert world.created == []
    assert not world.committed


def test_an_order_with_no_audience_is_a_422(client: TestClient, world: World) -> None:
    """``user_ids`` lost its ``min_length`` when ``group_ids`` arrived. Say who."""
    response = _post(client, course_id=str(COURSE_A))

    assert response.status_code == 422, response.text
    assert world.created == []


def test_a_course_and_a_folder_together_is_still_a_422(
    client: TestClient, world: World
) -> None:
    """The target stayed exclusive while the audience became additive."""
    response = _post(
        client,
        course_id=str(COURSE_A),
        folder_id=str(FOLDER_ID),
        group_ids=[str(TARDE)],
    )

    assert response.status_code == 422, response.text


def test_an_order_too_large_for_one_request_is_refused_by_size(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 422 naming the number, not a proxy timeout on a half-built response.

    (people x courses) is what the write actually costs. The limit is lowered here so the
    assertion is about the rule and not about how many fake people fit in a fixture.
    """
    monkeypatch.setattr(enrollment_service_module, "MAX_ASSIGNMENT_PAIRS", 2)

    response = _post(client, folder_id=str(FOLDER_ID), group_ids=[str(TARDE)])

    assert response.status_code == 422, response.text
    assert "4" in response.json()["detail"]  # 2 people x 2 courses
    assert world.created == []


# --------------------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------------------
def test_rows_created_by_one_group_remember_it(
    client: TestClient, world: World
) -> None:
    _post(client, course_id=str(COURSE_A), group_ids=[str(TARDE)])

    assert {row.source_group_id for row in world.created} == {TARDE}


def test_provenance_is_recorded_per_person_not_per_order(
    client: TestClient, world: World
) -> None:
    """Bruno is in both groups; Ana and Carla in one each.

    Stamping one group id on the whole order would be a coin toss written down as fact
    for Bruno — and the point of the column is a record that can later be trusted to
    answer "what did this group assign". So it is per person: unambiguous members get
    their group, Bruno gets nothing.
    """
    _post(client, course_id=str(COURSE_A), group_ids=[str(TARDE), str(MANANA)])

    by_user = {row.user_id: row.source_group_id for row in world.created}
    assert by_user[ANA] == TARDE
    assert by_user[CARLA] == MANANA
    assert by_user[BRUNO] is None


def test_a_person_named_explicitly_is_never_attributed_to_a_group(
    client: TestClient, world: World
) -> None:
    """Ana is named *and* in the group. The group did not put her there.

    If it were recorded as the group's doing, a future "take back what this group
    assigned" would revoke a course the admin granted to her by hand.
    """
    _post(
        client,
        course_id=str(COURSE_A),
        user_ids=[str(ANA)],
        group_ids=[str(TARDE)],
    )

    by_user = {row.user_id: row.source_group_id for row in world.created}
    assert by_user[ANA] is None
    assert by_user[BRUNO] == TARDE


def test_a_row_that_already_existed_does_not_get_claimed_by_the_group(
    client: TestClient, world: World
) -> None:
    """Idempotency means the group did not create it, so it does not own it."""
    world.existing.add((ANA, COURSE_A))

    body = _post(client, course_id=str(COURSE_A), group_ids=[str(TARDE)]).json()

    assert body["skipped_existing_count"] == 1
    assert body["created_count"] == 1
    assert {row.user_id for row in world.created} == {BRUNO}


# --------------------------------------------------------------------------------------
# The shape of the answer
# --------------------------------------------------------------------------------------
def test_the_old_request_shape_still_answers_a_bare_list(
    client: TestClient, world: World
) -> None:
    """The contract three screens depend on, unchanged.

    ``{course_id, user_ids}`` with no ``group_ids`` is the request this endpoint has
    always taken, and it must still come back as a list of enrollments rather than a
    counts object nobody's `.map()` can read.
    """
    response = _post(client, course_id=str(COURSE_A), user_ids=[str(ANA)])

    assert response.status_code == 201, response.text
    body = response.json()
    assert isinstance(body, list)
    assert body[0]["user_id"] == str(ANA)
    assert body[0]["course_title"] == "Bienvenida"


def test_naming_a_group_switches_the_answer_to_counts(
    client: TestClient, world: World
) -> None:
    body = _post(client, course_id=str(COURSE_A), group_ids=[str(TARDE)]).json()

    assert isinstance(body, dict)
    assert body["course_count"] == 1
    assert {row["user_id"] for row in body["enrollments"]} == {str(ANA), str(BRUNO)}


def test_the_echoed_rows_are_capped_and_say_so(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A group assignment can create thousands of rows; the response must not.

    Truncating silently would be worse than not echoing at all — a caller counting the
    list would conclude the rest were never created.
    """
    monkeypatch.setattr(enrollments_routes, "ENROLLMENT_ECHO_LIMIT", 1)

    body = _post(client, course_id=str(COURSE_A), group_ids=[str(TARDE)]).json()

    assert body["created_count"] == 2
    assert len(body["enrollments"]) == 1
    assert body["enrollments_truncated"] is True


# --------------------------------------------------------------------------------------
# Cost
# --------------------------------------------------------------------------------------
def test_the_existing_enrollments_are_read_once_for_the_whole_batch(
    client: TestClient, world: World
) -> None:
    """The read half of the loop is one query, not one per (person, course).

    Two people times two courses used to be four ``get_by_user_and_course`` round-trips;
    a folder assigned to a real group was thousands. The snapshot answers for the whole
    cross-product, and only a pair it reports as *already there* is fetched individually.
    """
    world.existing.add((ANA, COURSE_A))

    response = client.post(
        f"{PREFIX}/enrollments",
        json={"folder_id": str(FOLDER_ID), "group_ids": [str(TARDE)]},
    )

    assert response.status_code == 201, response.text
    assert world.pair_lookups == 1
    # Only the one pair the snapshot flagged as existing was read row by row.
    assert world.single_lookups == 1


# --------------------------------------------------------------------------------------
# The other door: the library's own folder assignment
# --------------------------------------------------------------------------------------
def test_the_folder_endpoint_takes_groups_too(
    client: TestClient, world: World
) -> None:
    """Same field, same resolution, same counts — it is the same operation reversed."""
    response = client.post(
        f"{PREFIX}/course-folders/{FOLDER_ID}/assign",
        json={"group_ids": [str(TARDE)], "deadline": "2026-12-31"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["course_count"] == 2
    assert body["created_count"] == 4  # 2 people x 2 published courses
    assert body["person_count"] == 2
    assert body["skipped_inactive_count"] == 1
    assert {str(row.deadline) for row in world.created} == {"2026-12-31"}


def test_the_folder_endpoint_still_refuses_an_order_naming_nobody(
    client: TestClient, world: World
) -> None:
    response = client.post(
        f"{PREFIX}/course-folders/{FOLDER_ID}/assign", json={"user_ids": []}
    )

    assert response.status_code == 422, response.text
    assert world.created == []
