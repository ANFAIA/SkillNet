"""Who may reach the v2 runtime surface, and with whose data (§11.3).

With a valid session, *which* courses does an employee get to touch?

The answer must be "the ones assigned to them", the same answer v1 gives in
``src/routes/courses.py``. Org scoping is not an access rule -- every colleague shares an
``org_id`` -- so ``get_scoped`` alone let any authenticated employee enumerate the node
graph, probe, render, answer and give feedback on a course nobody assigned them, and make
``POST /nodes/{id}/render`` spend real tokens doing it.

Three more properties live here because they are route-shaped and need no database:

* ``GET /nodes/{id}/renders/{render_id}`` is authorized by ``node_render_views``, not by
  the organisation — the render row is shared by the whole bucket.
* ``POST /nodes/{id}/events`` attributes every event to the **path** node.
* ``GET /render-kit`` serves the frozen catalogue and not the system prompt.

No database and no network: the session dependency is a stub and the repositories the
routes name are replaced with in-memory doubles. Router-level dependencies resolve before
the route body, so the LLM providers are exercised too — they degrade to ``None`` against
the stub, exactly as they are written to.
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
from src.models import NodeRenderStatus, UserRole
from src.routes import nodes as nodes_routes

PREFIX = "/api/v1"

ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
OTHER_ORG_ID = uuid.UUID("1111ffff-1111-1111-1111-111111111111")
USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
COURSE_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
NODE_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
RENDER_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")


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
    schema_version: int = 1
    delivery_mode: str = "dynamic"


@dataclass
class FakeNode:
    id: uuid.UUID = NODE_ID
    org_id: uuid.UUID = ORG_ID
    course_id: uuid.UUID = COURSE_ID
    title: str = "Plazo de devolucion"
    summary: str = "30 dias naturales."
    criticality: str = "recommended"
    position: int = 1
    archived: bool = False
    skill_id: uuid.UUID | None = None
    reviewed_at: Any = None
    mastery_threshold: float | None = None
    probe_items: list = field(default_factory=list)
    seed_lesson_id: uuid.UUID | None = None


@dataclass
class FakeRender:
    id: uuid.UUID = RENDER_ID
    node_id: uuid.UUID = NODE_ID
    org_id: uuid.UUID = ORG_ID
    ui_format: str = "explanation"
    status: NodeRenderStatus = NodeRenderStatus.READY
    backend: str = "openui"
    dialect: str = 'root = Stack([], "md")\n'
    #: The two columns a response model must never be able to reach.
    ui_spec: dict = field(default_factory=dict)
    answer_key: dict = field(default_factory=lambda: {"q1": {"correct": 1}})


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
    """Enough of ``AsyncSession`` for dependency resolution; it holds no data."""

    async def execute(self, _query: Any) -> FakeResult:
        return FakeResult([])

    async def get(self, _model: Any, _pk: Any) -> None:
        return None

    def add(self, _obj: Any) -> None:  # pragma: no cover - nothing writes here
        raise AssertionError("no route in this file may write")

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


@dataclass
class World:
    """What the doubles will answer with, mutated per test."""

    enrolled: bool = True
    node: FakeNode | None = None
    course: FakeCourse | None = None
    render: FakeRender | None = None
    viewed: bool = True
    recorded_events: list[Any] = field(default_factory=list)


def _install(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    """Replace the repositories ``src/routes/nodes.py`` names with doubles."""

    class FakeCourseRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_scoped(self, course_id: uuid.UUID, org_id: uuid.UUID):
            course = world.course
            if course is None or course.id != course_id or course.org_id != org_id:
                return None
            return course

        async def get_by_id(self, course_id: uuid.UUID):
            course = world.course
            return course if course is not None and course.id == course_id else None

    class FakeNodeRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_scoped(self, node_id: uuid.UUID, org_id: uuid.UUID):
            node = world.node
            if node is None or node.id != node_id or node.org_id != org_id:
                return None
            return node

        async def list_for_course(self, _course_id: uuid.UUID, include_archived: bool = False):
            return [world.node] if world.node is not None else []

        async def prerequisites_for(self, _node_ids):
            return {}

    class FakeEnrollmentRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_by_user_and_course(self, _user_id: uuid.UUID, _course_id: uuid.UUID):
            return object() if world.enrolled else None

    class FakeStateRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def states_for_nodes(self, *, user_id: uuid.UUID, node_ids):
            return {}

    class FakeRenderRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_scoped(self, render_id: uuid.UUID, org_id: uuid.UUID):
            render = world.render
            if render is None or render.id != render_id or render.org_id != org_id:
                return None
            return render

    class FakeViewRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get(self, *, user_id: uuid.UUID, render_id: uuid.UUID):
            return object() if world.viewed else None

    class RecordingProfileService:
        async def record_events(self, *, user_id: uuid.UUID, events) -> None:
            world.recorded_events.extend(events)

    monkeypatch.setattr(nodes_routes, "CourseRepository", FakeCourseRepo)
    monkeypatch.setattr(nodes_routes, "CourseNodeRepository", FakeNodeRepo)
    monkeypatch.setattr(nodes_routes, "EnrollmentRepository", FakeEnrollmentRepo)
    monkeypatch.setattr(nodes_routes, "LearnerNodeStateRepository", FakeStateRepo)
    monkeypatch.setattr(nodes_routes, "NodeRenderRepository", FakeRenderRepo)
    monkeypatch.setattr(nodes_routes, "NodeRenderViewRepository", FakeViewRepo)
    monkeypatch.setattr(nodes_routes, "resolve_delivery", lambda *_a, **_k: "dynamic")
    monkeypatch.setattr(
        nodes_routes, "_profile_service", lambda _db: RecordingProfileService()
    )


@pytest.fixture
def world() -> World:
    return World(node=FakeNode(), course=FakeCourse(), render=FakeRender())


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> TestClient:
    _install(monkeypatch, world)
    app = create_app()
    app.dependency_overrides[get_async_session] = lambda: StubSession()
    app.dependency_overrides[current_user] = lambda: FakeUser()
    return TestClient(app, raise_server_exceptions=False)


def as_admin(client: TestClient) -> None:
    client.app.dependency_overrides[current_user] = lambda: FakeUser(
        role=UserRole.ADMIN
    )


# --------------------------------------------------------------------------------------
# The enrollment gate
# --------------------------------------------------------------------------------------
#: One entry per employee-surface path that reads or writes learner data for a node. Every
#: one of them goes through ``_load_dynamic_node`` or ``list_course_nodes``, so this list is
#: what turns "the helper checks enrollment" into "no route forgot to use the helper".
GATED: tuple[tuple[str, str, dict | None], ...] = (
    ("GET", f"/courses/{COURSE_ID}/nodes", None),
    ("POST", f"/nodes/{NODE_ID}/probe", None),
    (
        "POST",
        f"/nodes/{NODE_ID}/probe/answer",
        {"probe_id": str(uuid.uuid4()), "item_id": "a", "answer": {"selected": 0}},
    ),
    ("POST", f"/nodes/{NODE_ID}/render", {"force": False}),
    ("GET", f"/nodes/{NODE_ID}/render", None),
    ("GET", f"/nodes/{NODE_ID}/renders", None),
    ("GET", f"/nodes/{NODE_ID}/renders/{RENDER_ID}", None),
    ("GET", f"/nodes/{NODE_ID}/render/stream?request_id=abc", None),
    (
        "POST",
        f"/nodes/{NODE_ID}/answer",
        {"render_id": str(RENDER_ID), "item_id": "q1", "answer": {"selected": 0}},
    ),
    ("POST", f"/nodes/{NODE_ID}/hint", {"render_id": str(RENDER_ID), "item_id": "q1"}),
    ("POST", f"/nodes/{NODE_ID}/feedback", {"difficulty": "ok"}),
    ("POST", f"/nodes/{NODE_ID}/events", {"events": []}),
)


@pytest.mark.parametrize(("method", "path", "body"), GATED)
def test_an_unenrolled_employee_is_forbidden_everywhere(
    client: TestClient, world: World, method: str, path: str, body: dict | None
) -> None:
    world.enrolled = False
    response = client.request(
        method, f"{PREFIX}{path}", **({"json": body} if body is not None else {})
    )
    assert response.status_code == 403, response.text
    body_json = response.json()
    assert body_json["code"] == "FORBIDDEN"
    assert "not enrolled" in body_json["detail"].lower()


def test_an_enrolled_employee_gets_the_node_list(client: TestClient) -> None:
    response = client.get(f"{PREFIX}/courses/{COURSE_ID}/nodes")
    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["id"] for row in body["nodes"]] == [str(NODE_ID)]


def test_an_admin_needs_no_enrollment(client: TestClient, world: World) -> None:
    """The preview of §11.3 and the waiver of §7.4 are creator tools: nobody enrolls the
    person reviewing the course."""
    world.enrolled = False
    as_admin(client)
    response = client.get(f"{PREFIX}/courses/{COURSE_ID}/nodes")
    assert response.status_code == 200, response.text


def test_an_unenrolled_employee_cannot_even_learn_the_course_exists(
    client: TestClient, world: World
) -> None:
    """A course of another organisation stays a 404; the 403 above is only ever for a
    course the caller's org owns. Neither answer confirms anything about content."""
    world.enrolled = False
    world.course = FakeCourse(org_id=OTHER_ORG_ID)
    world.node = FakeNode(org_id=OTHER_ORG_ID)
    assert client.get(f"{PREFIX}/courses/{COURSE_ID}/nodes").status_code == 404
    assert client.post(f"{PREFIX}/nodes/{NODE_ID}/probe").status_code == 404


# --------------------------------------------------------------------------------------
# GET /nodes/{node_id}/renders/{render_id}
# --------------------------------------------------------------------------------------
def test_a_render_this_learner_never_saw_is_not_theirs_to_open(
    client: TestClient, world: World
) -> None:
    """``node_renders`` is shared by the whole bucket, so "in my organisation" is not
    authorization: it would hand a learner screens nobody ever served them. The
    ``node_render_views`` row is the record that they were."""
    assert world.render is not None
    world.viewed = False

    response = client.get(f"{PREFIX}/nodes/{NODE_ID}/renders/{RENDER_ID}")
    assert response.status_code == 404, response.text


def test_a_previous_version_can_be_reopened_without_its_answer_key(
    client: TestClient, world: World
) -> None:
    """The endpoint the version list of §5.5 was missing — and the projection is the same
    ``ServedRender`` the pinned route uses, so ``answer_key`` cannot travel."""
    assert world.render is not None

    response = client.get(f"{PREFIX}/nodes/{NODE_ID}/renders/{RENDER_ID}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["render_id"] == str(RENDER_ID)
    assert body["program"] == world.render.dialect
    assert body["shell_mode"] == "legacy_stepper"
    assert "answer_key" not in body
    assert "ui_spec" not in body


def test_previous_episode_version_exposes_its_own_shell_mode(
    client: TestClient, world: World
) -> None:
    assert world.render is not None
    world.render.ui_spec = {
        "generation": {
            "shell_mode": "episode",
            "generation_policy_key": "adaptive-episodes/v4",
            "episode_status": "ready",
        }
    }

    response = client.get(f"{PREFIX}/nodes/{NODE_ID}/renders/{RENDER_ID}")

    assert response.status_code == 200, response.text
    assert response.json()["shell_mode"] == "episode"


# --------------------------------------------------------------------------------------
# POST /nodes/{node_id}/events
# --------------------------------------------------------------------------------------
def test_an_event_cannot_name_its_own_node(client: TestClient, world: World) -> None:
    """``learning_events.node_id`` steers ``format_vector`` — and therefore the learner's
    ``cache_key`` bucket and the ``revisar_prerrequisito`` signal. Its only backstop used to
    be a foreign key, which accepts any node in any organisation."""
    foreign = uuid.uuid4()
    rejected = client.post(
        f"{PREFIX}/nodes/{NODE_ID}/events",
        json={"events": [{"type": "view", "node_id": str(foreign)}]},
    )
    assert rejected.status_code == 422, rejected.text
    assert world.recorded_events == []


def test_every_event_is_attributed_to_the_path_node(
    client: TestClient, world: World
) -> None:
    response = client.post(
        f"{PREFIX}/nodes/{NODE_ID}/events",
        json={"events": [{"type": "view", "element": "texto"}]},
    )
    assert response.status_code == 204, response.text
    assert [event.node_id for event in world.recorded_events] == [NODE_ID]


# --------------------------------------------------------------------------------------
# GET /render-kit
# --------------------------------------------------------------------------------------
def test_the_render_kit_is_served_and_matches_the_build_artefacts(
    client: TestClient,
) -> None:
    """§11.3 promised this endpoint and nothing implemented it, so the browser had no
    served contract for the frozen kit at all."""
    from src.render.prompt import catalog_version, load_artifact

    response = client.get(f"{PREFIX}/render-kit")
    assert response.status_code == 200, response.text
    body = response.json()

    artifact = load_artifact()
    assert body["catalog_version"] == catalog_version()
    assert body["catalog_digest"] == artifact.catalog_digest
    assert body["root"] == artifact.root
    assert [component["name"] for component in body["components"]] == list(
        artifact.component_names
    )
    # The system prompt is an audit artefact, not an API surface.
    assert "prompt" not in body
    assert all("prompt" not in key for key in body)
