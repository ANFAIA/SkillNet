"""``POST /nodes/{id}/complete`` — the half of progress that mastery cannot express.

This route writes ``learner_node_states.completed_at`` (migration 0029) and nothing else,
and it is the entire reason that column exists. Rule 6 of §7.3 only reaches ``mastered``
through a streak of correct answers on **graded** items; an expository node — a summary, a
worked example, a checklist — has no graded item to offer, so it stays ``not_started``
however completely it was read. Before the stamp, a course built out of such nodes
reported 0% for ever and could never close: the learner finished it and the bar never
moved.

Four properties are pinned here, and each of them is a way the feature can silently
regress into that same hole:

1. **The motivating path, end to end.** Three expository nodes, three ``POST /complete``,
   and the course reaches 100%, says ``can_complete``, and the enrollment closes. Nothing
   else in the suite walks it, and it is the one that was broken.
2. **Idempotence, in both halves.** ``mark_completed`` never moves a stamp already there,
   and ``close_dynamic_if_mastered`` is a recompute that no-ops once the enrollment agrees
   with the verdict. Together they are what lets a client fire this on every "next node"
   press without tracking whether it already did — so if either half stops holding, the
   client's write path becomes wrong rather than merely wasteful.
3. **``state`` and ``mastery`` are not touched.** ``completed_at`` and the evidence
   machine are orthogonal axes on purpose: reaching the last screen is not a
   demonstration, and writing a mastery number here would put an invented figure on the
   scale ``CourseCompletion.score`` averages and a certificate prints.
4. **What the body returns.** ``progress_percent`` and ``can_complete`` come back with the
   stamp so one round trip both records the node and refreshes the course bar; a client
   that had to derive them would show a stale percentage next to a node it just finished.

No database and no network, the technique of ``tests/test_node_resume_marker.py``: the
session dependency is a stub and the repositories the routes name are in-memory doubles.
Two things are deliberately **real** rather than doubled, because they are what is under
test — ``LearnerNodeStateRepository.mark_completed`` (where "stamp once" lives) and
``EnrollmentService.close_dynamic_if_mastered`` together with
``mastery_service.evaluate_course_completion`` (where "done" and the closing rule live).
The doubles therefore also stand in for the two repositories ``EnrollmentService`` names
in its own module, so the closure reads the same in-memory world the route wrote to.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.deps.auth import current_user
from src.deps.db import get_async_session
from src.main import create_app
from src.models import EnrollmentStatus, UserRole
from src.repositories.learner_node_state_repo import LearnerNodeStateRepository
from src.routes import nodes as nodes_routes
from src.services import enrollment_service as enrollment_service_module

PREFIX = "/api/v1"

ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
COURSE_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")

#: Three expository nodes: no probe items, nothing graded, so ``mastered`` is unreachable
#: for all three and ``completed_at`` is the only thing that can move the bar.
NODE_IDS = (
    uuid.UUID("44444444-4444-4444-4444-444444444441"),
    uuid.UUID("44444444-4444-4444-4444-444444444442"),
    uuid.UUID("44444444-4444-4444-4444-444444444443"),
)


# --------------------------------------------------------------------------------------
# Doubles
# --------------------------------------------------------------------------------------
@dataclass
class FakeUser:
    id: uuid.UUID = USER_ID
    org_id: uuid.UUID = ORG_ID
    role: UserRole = UserRole.EMPLOYEE
    accessibility: dict = field(default_factory=dict)


@dataclass
class FakeCourse:
    """Dynamic for the **real** ``resolve_delivery``, not for a patched one.

    Both halves are spelled out because that function is the single decision point and
    ``close_dynamic_if_mastered`` consults it again from its own module: faking the
    verdict in one place would leave the other one reading a static course.
    """

    id: uuid.UUID = COURSE_ID
    org_id: uuid.UUID = ORG_ID
    schema_version: int = 3
    delivery_mode: str = "dynamic"
    schema_status: str = "validated"
    #: Read by the learner gate in ``services/course_access.py``.
    status: str = "published"


@dataclass
class FakeNode:
    id: uuid.UUID
    position: int
    title: str
    org_id: uuid.UUID = ORG_ID
    course_id: uuid.UUID = COURSE_ID
    summary: str | None = None
    criticality: str = "recommended"
    archived: bool = False
    reviewed_at: Any = None


@dataclass
class FakeEnrollment:
    """The four ``enrollments`` columns §7.5 writes when a dynamic course closes."""

    status: EnrollmentStatus = EnrollmentStatus.IN_PROGRESS
    started_at: datetime | None = None
    completed_at: datetime | None = None
    score: float | None = None
    id: uuid.UUID = uuid.UUID("77777777-7777-7777-7777-777777777777")
    user_id: uuid.UUID = USER_ID
    course_id: uuid.UUID = COURSE_ID


@dataclass
class FakeState:
    """The ``learner_node_states`` columns this route reads, writes and echoes.

    ``state`` and ``mastery`` are here so the test can watch them **not** move.
    """

    node_id: uuid.UUID
    user_id: uuid.UUID = USER_ID
    state: str = "not_started"
    mastery: float = 0.0
    completed_at: datetime | None = None
    first_seen_at: datetime | None = None


class FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalar_one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalars(self) -> FakeResult:
        return self

    def all(self) -> list[Any]:
        return list(self._rows)

    def first(self) -> Any:
        return self._rows[0] if self._rows else None


class StubSession:
    """Counts flushes so "written once" is observable rather than inferred.

    Empty results are the right answer for the one query this path issues on its own:
    ``_assign_course_skills`` looks up ``course_skills`` after a close, and a course with
    no linked skill grants none.
    """

    def __init__(self) -> None:
        self.flushes = 0

    async def execute(self, _query: Any) -> FakeResult:
        return FakeResult([])

    async def get(self, _model: Any, _pk: Any) -> None:
        return None

    def add(self, _obj: Any) -> None:
        return None

    async def flush(self) -> None:
        self.flushes += 1

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


@dataclass
class World:
    course: FakeCourse = field(default_factory=FakeCourse)
    nodes: list[FakeNode] = field(
        default_factory=lambda: [
            FakeNode(id=NODE_IDS[0], position=1, title="Que es un sesgo"),
            FakeNode(id=NODE_IDS[1], position=2, title="Ejemplo resuelto"),
            FakeNode(id=NODE_IDS[2], position=3, title="Resumen"),
        ]
    )
    states: dict[uuid.UUID, FakeState] = field(default_factory=dict)
    #: ``None`` models the admin previewing a course nobody enrolled them in.
    enrollment: FakeEnrollment | None = field(default_factory=FakeEnrollment)

    def state_for(self, node_id: uuid.UUID) -> FakeState:
        row = self.states.get(node_id)
        if row is None:
            row = FakeState(node_id=node_id)
            self.states[node_id] = row
        return row


class FakeStateRepo:
    """In-memory ``learner_node_states``.

    ``mark_completed`` is delegated to the **real** repository method bound to this
    double: "stamp only when empty" is the rule under test and re-implementing it here
    would test the test.
    """

    def __init__(self, world: World, session: StubSession) -> None:
        self.world = world
        self.session = session

    async def get_by_user_and_node(self, _user_id: uuid.UUID, node_id: uuid.UUID):
        return self.world.states.get(node_id)

    async def get_or_create(
        self, *, user_id: uuid.UUID, node_id: uuid.UUID, mastery: float = 0.0
    ):
        return self.world.state_for(node_id)

    async def states_for_nodes(self, *, user_id: uuid.UUID, node_ids: Any):
        wanted = set(node_ids)
        return {
            node_id: row
            for node_id, row in self.world.states.items()
            if node_id in wanted
        }

    async def unmastered_prerequisites(self, *, user_id: uuid.UUID, node_id: uuid.UUID):
        return []

    async def mark_completed(
        self, *, user_id: uuid.UUID, node_id: uuid.UUID, now: datetime | None = None
    ):
        return await LearnerNodeStateRepository.mark_completed(
            self, user_id=user_id, node_id=node_id, now=now
        )


def _install(monkeypatch: pytest.MonkeyPatch, world: World, session: StubSession) -> None:
    class FakeCourseRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_scoped(self, course_id: uuid.UUID, org_id: uuid.UUID):
            course = world.course
            if course.id != course_id or course.org_id != org_id:
                return None
            return course

        async def get_by_id(self, course_id: uuid.UUID):
            return world.course if world.course.id == course_id else None

    class FakeNodeRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_scoped(self, node_id: uuid.UUID, org_id: uuid.UUID):
            return next(
                (n for n in world.nodes if n.id == node_id and n.org_id == org_id), None
            )

        async def list_for_course(
            self, _course_id: uuid.UUID, include_archived: bool = False
        ):
            return [n for n in world.nodes if include_archived or not n.archived]

        async def prerequisites_for(self, _node_ids: Any):
            return {}

    class FakeEnrollmentRepo:
        def __init__(self, db: Any) -> None:
            #: ``EnrollmentService`` builds three more repositories out of this attribute
            #: and flushes through it, so the double has to carry the session too.
            self.session = db

        async def get_by_user_and_course(
            self, _user_id: uuid.UUID, _course_id: uuid.UUID
        ):
            return world.enrollment

    def state_repo(_db: Any) -> FakeStateRepo:
        return FakeStateRepo(world, session)

    monkeypatch.setattr(nodes_routes, "CourseRepository", FakeCourseRepo)
    monkeypatch.setattr(nodes_routes, "CourseNodeRepository", FakeNodeRepo)
    monkeypatch.setattr(nodes_routes, "EnrollmentRepository", FakeEnrollmentRepo)
    monkeypatch.setattr(nodes_routes, "LearnerNodeStateRepository", state_repo)
    # ``EnrollmentService.node_progress`` builds these two from its **own** module, so
    # patching the route's names alone would leave the closure reading a real database.
    monkeypatch.setattr(
        enrollment_service_module, "CourseNodeRepository", FakeNodeRepo
    )
    monkeypatch.setattr(
        enrollment_service_module, "LearnerNodeStateRepository", state_repo
    )


@pytest.fixture
def world() -> World:
    return World()


@pytest.fixture
def session() -> StubSession:
    return StubSession()


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch, world: World, session: StubSession
) -> TestClient:
    _install(monkeypatch, world, session)
    app = create_app()
    app.dependency_overrides[get_async_session] = lambda: session
    app.dependency_overrides[current_user] = lambda: FakeUser()
    return TestClient(app, raise_server_exceptions=False)


def complete(client: TestClient, node_id: uuid.UUID) -> dict:
    response = client.post(f"{PREFIX}/nodes/{node_id}/complete")
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------------------
# 1. The case the column was added for
# --------------------------------------------------------------------------------------
def test_finishing_every_expository_node_completes_the_course(
    client: TestClient, world: World
) -> None:
    """The whole point, walked end to end.

    Not one of these three nodes has a graded item, so not one of them can ever be
    ``mastered``. Before ``completed_at`` this course was stuck at 0% and unclosable
    however thoroughly it was read — the bug the migration was written for.
    """
    assert world.enrollment is not None

    for node_id in NODE_IDS:
        body = complete(client, node_id)

    assert body["progress_percent"] == 100
    assert body["can_complete"] is True
    assert world.enrollment.status is EnrollmentStatus.COMPLETED
    assert world.enrollment.completed_at is not None
    # And it closes with a *low* score, which is the distinction the design keeps: `score`
    # averages measured mastery only, so a course finished by reading it is on the record
    # as exactly that. Closing and being good at it are two different facts.
    assert world.enrollment.score == pytest.approx(0.0)


def test_the_bar_moves_one_node_at_a_time_and_only_the_last_one_closes(
    client: TestClient, world: World
) -> None:
    """``progress_percent`` and ``can_complete`` in the body, node by node.

    They are returned by this route so a client needs no second request and cannot show a
    stale bar next to a node it has just finished. ``can_complete`` stays false while any
    node is outstanding — the two answers come from one ``blocked`` set, so they can never
    disagree about whether the course is finished.
    """
    assert world.enrollment is not None
    seen = []
    for node_id in NODE_IDS:
        body = complete(client, node_id)
        seen.append((body["progress_percent"], body["can_complete"]))

    assert seen == [(33, False), (67, False), (100, True)]
    # Nothing closed early: the first two calls left the enrollment where it was.
    assert world.enrollment.status is EnrollmentStatus.COMPLETED


def test_progress_is_reported_even_with_no_enrollment(
    client: TestClient, world: World
) -> None:
    """An admin previewing a course they were never assigned still gets real numbers.

    ``close_dynamic_if_mastered`` returns ``(None, completion)`` in that case — no row to
    move, but a verdict all the same — and the route reports the verdict. The alternative
    (0% for anyone without an enrollment) would make the preview lie about the course.

    An admin, because they are the only role the learner gate lets through unenrolled: an
    employee without an enrollment is refused by ``assert_learner_can_open`` long before
    anything is stamped.
    """
    world.enrollment = None
    client.app.dependency_overrides[current_user] = lambda: FakeUser(
        role=UserRole.ADMIN
    )

    body = complete(client, NODE_IDS[0])

    assert body["progress_percent"] == 33
    assert body["can_complete"] is False


# --------------------------------------------------------------------------------------
# 2. Idempotence, in both halves
# --------------------------------------------------------------------------------------
def test_a_second_call_does_not_move_the_stamp(
    client: TestClient, world: World
) -> None:
    """Re-reading a node the learner already finished must not rewrite *when*.

    ``completed_at`` is part of the evidence a certificate is justified with, and the
    client is invited to call this on every "next node" press: if the stamp drifted, "when
    did they finish this" would decay into "when were they last here".
    """
    first = complete(client, NODE_IDS[0])["completed_at"]
    stamped = world.states[NODE_IDS[0]].completed_at
    assert stamped is not None

    again = complete(client, NODE_IDS[0])["completed_at"]

    assert again == first
    assert world.states[NODE_IDS[0]].completed_at == stamped


def test_the_stamp_is_written_once_and_not_on_every_call(
    session: StubSession, world: World
) -> None:
    """The repository rule on its own, asserted through ``flush``.

    A value comparison would also pass if the second call rewrote the same instant with a
    frozen clock; "did not write" is the actual property, so count the writes.
    """
    repo = FakeStateRepo(world, session)
    first = datetime(2026, 8, 28, 9, 0, tzinfo=timezone.utc)
    later = datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc)

    asyncio.run(repo.mark_completed(user_id=USER_ID, node_id=NODE_IDS[0], now=first))
    assert world.states[NODE_IDS[0]].completed_at == first
    assert session.flushes == 1

    asyncio.run(repo.mark_completed(user_id=USER_ID, node_id=NODE_IDS[0], now=later))
    assert world.states[NODE_IDS[0]].completed_at == first
    assert session.flushes == 1


def test_a_finished_course_is_not_closed_twice(
    client: TestClient, world: World
) -> None:
    """The other half: ``close_dynamic_if_mastered`` is a recompute, not an event.

    Once the enrollment agrees with the §7.5 verdict there is nothing to apply, so a
    repeated call must leave ``completed_at`` where it is. A moving completion date would
    be a course that finished again every time the learner reopened its last screen.
    """
    for node_id in NODE_IDS:
        complete(client, node_id)
    assert world.enrollment is not None
    closed_at = world.enrollment.completed_at
    assert closed_at is not None

    complete(client, NODE_IDS[2])

    assert world.enrollment.status is EnrollmentStatus.COMPLETED
    assert world.enrollment.completed_at == closed_at


# --------------------------------------------------------------------------------------
# 3. completed_at and the evidence machine are orthogonal
# --------------------------------------------------------------------------------------
def test_completing_a_node_leaves_state_and_mastery_alone(
    client: TestClient, world: World
) -> None:
    """Reaching the last screen is not a demonstration of anything.

    Moving ``state`` here would let reading a node claim the mastery a graded streak is
    supposed to prove, and moving ``mastery`` would put an invented number on the same
    scale as measured ones — the scale ``CourseCompletion.score`` averages onto a
    certificate. The response echoes both untouched, which is what makes a client seeing
    ``not_started`` beside a timestamp read the two columns doing their two jobs.
    """
    body = complete(client, NODE_IDS[0])

    assert body["state"] == "not_started"
    assert body["mastery"] == pytest.approx(0.0)
    assert body["completed_at"] is not None
    row = world.states[NODE_IDS[0]]
    assert row.state == "not_started"
    assert row.mastery == pytest.approx(0.0)


def test_completing_a_mastered_node_does_not_demote_it(
    client: TestClient, world: World
) -> None:
    """Orthogonality in the other direction, and the reason ``score`` still means something.

    A learner who mastered a node and then pressed "next" must keep the mastery they
    demonstrated: ``node_is_done`` already counted the node, so the stamp adds nothing to
    progress here — but a route that wrote ``state`` would erase real evidence, and the
    course would close at a score it did not earn.
    """
    mastered = world.state_for(NODE_IDS[0])
    mastered.state = "mastered"
    mastered.mastery = 0.9

    body = complete(client, NODE_IDS[0])

    assert body["state"] == "mastered"
    assert body["mastery"] == pytest.approx(0.9)
    assert world.states[NODE_IDS[0]].mastery == pytest.approx(0.9)
    # Already done before the stamp, so the bar does not double-count it.
    assert body["progress_percent"] == 33


def test_a_mastered_and_a_read_node_are_both_done_but_score_tells_them_apart(
    client: TestClient, world: World
) -> None:
    """``node_is_done`` is "mastered **or** finished", and ``score`` is the tiebreak.

    This is the one design decision the whole feature rests on, so it is asserted as a
    pair: closure treats the two ways of finishing a node identically, and the number a
    certificate prints does not.
    """
    demonstrated = world.state_for(NODE_IDS[0])
    demonstrated.state = "mastered"
    demonstrated.mastery = 0.9

    for node_id in NODE_IDS[1:]:
        body = complete(client, node_id)

    assert body["can_complete"] is True
    assert body["progress_percent"] == 100
    assert world.enrollment is not None
    assert world.enrollment.status is EnrollmentStatus.COMPLETED
    # 0.9 on one node, 0.0 on the two that were only read.
    assert world.enrollment.score == pytest.approx(0.3)
