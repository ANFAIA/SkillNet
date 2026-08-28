""""Where was I?" — the one field that answers it, and the one path that writes it.

The bug this file pins down was a data gap, not a UI one. Nothing in
``GET /courses/{id}/nodes`` could tell a client which node a learner had reached:

* ``state`` cannot. ``learning`` is only reachable by answering a **graded** item
  (rule 0 of §7.3), so an expository node, or a node whose five screens were read
  without answering anything, stays ``not_started``.
* the *existence* of the ``learner_node_states`` row cannot either, because opening a
  node **and** prefetching one both create it — ``NodeRenderService.pin`` calls
  ``get_or_create`` — so the row is there for three nodes ahead of wherever the learner
  actually is.

So a client asking "reopen the node in progress" always got the first one, which is the
reported symptom: leave the course, come back, start over.

``learner_node_states.first_seen_at`` answers it, and the two properties asserted here
are the ones that make it trustworthy:

1. **``GET /courses/{id}/nodes`` projects it**, so the decision is a read of a recorded
   fact rather than a guess over ``state``.
2. **Only ``GET /nodes/{id}/render`` stamps it** — the render being handed to a browser.
   ``POST /nodes/{id}/render`` is also fired by the anticipatory prefetch (``CourseView``
   fires two on course open, ``NodeView`` four ahead of the current node), so a stamp
   there would mark nodes nobody has looked at and the resume target would run away in
   front of the learner. And it is stamped **once**: ``first_seen_at`` is part of the
   evidence a certificate is justified with, so a re-read must not move it.

The same request writes two more facts about "the learner was handed the lesson", and they
are asserted here because they share that one moment and nothing else can observe it:

3. **The enrollment moves ``assigned -> in_progress``** and stamps ``started_at``. The
   dynamic branch had no such transition at all, so a course at 57% still read "Pendiente"
   and "Cursos activos" counted 0. Once, like the stamp above.
4. **A served ``fallback`` asks for one regeneration**, a ``ready`` render asks for none.
   ``ready`` is retained, ``fallback`` is not: the client stops calling ``POST /render``
   the moment ``GET /render`` has something served, so this is the only place that can
   retry a degraded screen.

No database and no network, same technique as ``tests/test_hint_ladder.py``: the session
dependency is a stub and the repositories the routes name are in-memory doubles. The
repository method under test (``mark_opened``) is the real one, running against a fake
row — which is where the "stamp once" rule actually lives.
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
from src.models import UserRole
from src.repositories.learner_node_state_repo import LearnerNodeStateRepository
from src.routes import nodes as nodes_routes
from src.services.node_render_service import ServedRender

PREFIX = "/api/v1"

ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
COURSE_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
NODE_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
AHEAD_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")
RENDER_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")

SEEN_AT = datetime(2026, 8, 26, 17, 30, tzinfo=timezone.utc)


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
    id: uuid.UUID = COURSE_ID
    org_id: uuid.UUID = ORG_ID
    schema_version: int = 3
    delivery_mode: str = "dynamic"
    #: `resolve_delivery` reads both halves, and `mark_dynamic_started` is gated on it.
    schema_status: str = "validated"


@dataclass
class FakeEnrollment:
    """The three ``enrollments`` columns the "started" transition touches."""

    status: str = "assigned"
    started_at: datetime | None = None
    id: uuid.UUID = uuid.UUID("77777777-7777-7777-7777-777777777777")
    user_id: uuid.UUID = USER_ID
    course_id: uuid.UUID = COURSE_ID


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
class FakeState:
    """The four ``learner_node_states`` columns this behaviour reads and writes."""

    node_id: uuid.UUID
    user_id: uuid.UUID = USER_ID
    state: str = "not_started"
    mastery: float = 0.0
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


class StubSession:
    """Counts flushes so "stamped once" is observable, not inferred."""

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
            FakeNode(id=NODE_ID, position=1, title="Plazo de devolucion"),
            FakeNode(id=AHEAD_ID, position=2, title="Excepciones"),
        ]
    )
    states: dict[uuid.UUID, FakeState] = field(default_factory=dict)
    #: Nodes the anticipatory prefetch has pinned a render for. These get a state row and
    #: no stamp — the distinction the whole feature rests on.
    created: list[uuid.UUID] = field(default_factory=list)
    enrollment: FakeEnrollment = field(default_factory=FakeEnrollment)
    #: Status of the render `GET /render` hands over. `fallback` is the degraded backup.
    served_status: str = "ready"
    #: Regenerations `GET /render` asked for. Empty is the assertion for a good render.
    regenerations: list[uuid.UUID] = field(default_factory=list)

    def state_for(self, node_id: uuid.UUID) -> FakeState:
        row = self.states.get(node_id)
        if row is None:
            row = FakeState(node_id=node_id)
            self.states[node_id] = row
            self.created.append(node_id)
        return row


class FakeStateRepo:
    """In-memory ``learner_node_states``. ``mark_opened`` is delegated to the **real**
    repository method, bound to this double: the "stamp only if empty" rule is the thing
    under test and must not be re-implemented here."""

    def __init__(self, world: World, session: StubSession) -> None:
        self.world = world
        self.session = session

    async def get_by_user_and_node(self, _user_id: uuid.UUID, node_id: uuid.UUID):
        return self.world.states.get(node_id)

    async def get_or_create(self, *, user_id: uuid.UUID, node_id: uuid.UUID, mastery: float = 0.0):
        return self.world.state_for(node_id)

    async def states_for_nodes(self, *, user_id: uuid.UUID, node_ids: Any):
        return {
            node_id: row
            for node_id, row in self.world.states.items()
            if node_id in set(node_ids)
        }

    async def unmastered_prerequisites(self, *, user_id: uuid.UUID, node_id: uuid.UUID):
        return []

    async def mark_opened(self, *, user_id: uuid.UUID, node_id: uuid.UUID, now=None):
        return await LearnerNodeStateRepository.mark_opened(
            self, user_id=user_id, node_id=node_id, now=now
        )


@dataclass
class FakeRender:
    id: uuid.UUID = RENDER_ID
    node_id: uuid.UUID = NODE_ID
    ui_format: str = "explanation"
    status: str = "ready"
    backend: str = "openui"
    shell_mode: str = "episode"
    cache_key: str = "safety:test:degraded"


def _served(status: str = "ready") -> ServedRender:
    return ServedRender(
        render_id=RENDER_ID,
        node_id=NODE_ID,
        ui_format="explanation",
        status=status,
        backend="openui",
        shell_mode="legacy_stepper" if status == "fallback" else "episode",
        cached=True,
        program='root = Stack([], "md")\n',
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

        async def list_for_course(self, _course_id: uuid.UUID, include_archived: bool = False):
            return list(world.nodes)

        async def prerequisites_for(self, _node_ids: Any):
            return {}

    class FakeEnrollmentRepo:
        def __init__(self, db: Any) -> None:
            self.session = db

        async def get_by_user_and_course(self, _user_id: uuid.UUID, _course_id: uuid.UUID):
            return world.enrollment

    class FakeRenderService:
        """Only the five members ``GET /nodes/{id}/render`` touches."""

        def __init__(self, _db: Any) -> None:
            pass

        def assert_reviewed(self, _node: Any) -> None:
            return None

        async def prebaked_preview(self, *, node: Any, bucket: str):
            return None

        async def pinned_render(self, **_kwargs: Any):
            return FakeRender(status=world.served_status)

        async def serve(self, *, user_id: uuid.UUID, render: Any, cached: bool):
            return _served(world.served_status)

        async def node_pack_ready(self, *, node: Any, course: Any) -> bool:
            return True

        async def request_render(self, *, user: Any, node: Any, course: Any):
            world.regenerations.append(node.id)
            return None

    monkeypatch.setattr(nodes_routes, "CourseRepository", FakeCourseRepo)
    monkeypatch.setattr(nodes_routes, "CourseNodeRepository", FakeNodeRepo)
    monkeypatch.setattr(nodes_routes, "EnrollmentRepository", FakeEnrollmentRepo)
    monkeypatch.setattr(nodes_routes, "NodeRenderService", FakeRenderService)
    monkeypatch.setattr(
        nodes_routes,
        "LearnerNodeStateRepository",
        lambda _db: FakeStateRepo(world, session),
    )
    monkeypatch.setattr(nodes_routes, "resolve_delivery", lambda *_a, **_k: "dynamic")


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


def list_nodes(client: TestClient) -> list[dict]:
    response = client.get(f"{PREFIX}/courses/{COURSE_ID}/nodes")
    assert response.status_code == 200, response.text
    return response.json()["nodes"]


# --------------------------------------------------------------------------------------
# 1. The field
# --------------------------------------------------------------------------------------
def test_the_node_list_reports_when_each_node_was_first_seen(
    client: TestClient, world: World
) -> None:
    """The projection. Without it the client has to guess from ``state``, and ``state``
    says ``not_started`` for a node that was read end to end."""
    world.state_for(NODE_ID).first_seen_at = SEEN_AT

    rows = {row["title"]: row for row in list_nodes(client)}
    assert rows["Plazo de devolucion"]["first_seen_at"] == "2026-08-26T17:30:00Z"
    # Never opened: no stamp, even though the row may well exist.
    assert rows["Excepciones"]["first_seen_at"] is None


def test_a_prefetched_node_is_not_reported_as_seen(
    client: TestClient, world: World
) -> None:
    """The distinction the resume target depends on.

    ``NodeRenderService.pin`` creates the ``learner_node_states`` row for every node the
    prefetch warms, so "the row exists" means nothing. Only a stamp does.
    """
    # What a prefetch leaves behind: a row, nothing else.
    world.state_for(AHEAD_ID)
    assert AHEAD_ID in world.created

    rows = {row["title"]: row for row in list_nodes(client)}
    assert rows["Excepciones"]["state"] == "not_started"
    assert rows["Excepciones"]["first_seen_at"] is None


# --------------------------------------------------------------------------------------
# 2. The one path that writes it
# --------------------------------------------------------------------------------------
def test_serving_a_render_stamps_the_node_as_seen(
    client: TestClient, world: World
) -> None:
    """``GET /nodes/{id}/render`` is the learner being handed the lesson. That is the
    moment the node counts as reached, and it is the only writer."""
    assert world.states.get(NODE_ID) is None

    response = client.get(f"{PREFIX}/nodes/{NODE_ID}/render")
    assert response.status_code == 200, response.text

    stamped = world.states[NODE_ID].first_seen_at
    assert stamped is not None
    assert list_nodes(client)[0]["first_seen_at"] is not None
    return_visit = client.get(f"{PREFIX}/nodes/{NODE_ID}/render")
    assert return_visit.status_code == 200
    # Never moved: `first_seen_at` is audit evidence, and a client reading "the newest
    # stamp" must get "the deepest node reached", not "the node refetched last".
    assert world.states[NODE_ID].first_seen_at == stamped


def test_the_stamp_is_written_once_and_not_on_every_read(
    session: StubSession, world: World
) -> None:
    """The repository rule on its own: a second call must not touch the row.

    Asserted through ``session.flush``, because "did not write" is the property and a
    value comparison would also pass if the second call rewrote the same instant.
    """
    repo = FakeStateRepo(world, session)

    first = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)
    later = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)

    asyncio.run(repo.mark_opened(user_id=USER_ID, node_id=NODE_ID, now=first))
    assert world.states[NODE_ID].first_seen_at == first
    assert session.flushes == 1

    asyncio.run(repo.mark_opened(user_id=USER_ID, node_id=NODE_ID, now=later))
    assert world.states[NODE_ID].first_seen_at == first
    assert session.flushes == 1


# --------------------------------------------------------------------------------------
# 3. The enrollment starts at the same moment
# --------------------------------------------------------------------------------------
def test_serving_a_render_starts_the_dynamic_enrollment(
    client: TestClient, world: World
) -> None:
    """A lesson on screen is what "started the course" means, and v2 had nobody saying it."""
    assert world.enrollment.status == "assigned"

    assert client.get(f"{PREFIX}/nodes/{NODE_ID}/render").status_code == 200

    assert world.enrollment.status == "in_progress"
    assert world.enrollment.started_at is not None


def test_a_second_visit_does_not_move_started_at(
    client: TestClient, world: World
) -> None:
    """Idempotent, because this runs on every served render (and TanStack refetches on
    window focus). "When did they begin" must not decay into "when were they last here"."""
    assert client.get(f"{PREFIX}/nodes/{NODE_ID}/render").status_code == 200
    first = world.enrollment.started_at
    assert first is not None

    assert client.get(f"{PREFIX}/nodes/{NODE_ID}/render").status_code == 200

    assert world.enrollment.started_at == first
    assert world.enrollment.status == "in_progress"


# --------------------------------------------------------------------------------------
# 4. ready is retained, fallback is not
# --------------------------------------------------------------------------------------
def test_a_served_fallback_asks_for_one_regeneration(
    client: TestClient, world: World
) -> None:
    """The degraded screen is still served — blanking it would be worse — and exactly one
    regeneration is requested, which rewrites the same ``cache_key`` in place."""
    world.served_status = "fallback"

    response = client.get(f"{PREFIX}/nodes/{NODE_ID}/render")

    assert response.status_code == 200, response.text
    assert response.json()["program"]
    assert world.regenerations == [NODE_ID]


def test_a_served_ready_render_asks_for_nothing(
    client: TestClient, world: World
) -> None:
    """The other half of the asymmetry, and the reason the pin exists: a good render is
    never reconsidered, so no tokens are spent on a revisit."""
    assert client.get(f"{PREFIX}/nodes/{NODE_ID}/render").status_code == 200
    assert client.get(f"{PREFIX}/nodes/{NODE_ID}/render").status_code == 200

    assert world.regenerations == []
