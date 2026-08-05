"""The §7.4 hint ladder, end to end over the HTTP surface — and the state it unlocks.

Until this file existed, one whole state of the system was **unreachable**. Rule 8 of
§7.3 (fourth failure of an item after three hints -> ``needs_review`` + worked solution)
requires ``hints_used >= HINT_LIMIT``, ``hints_used`` moves only through
``POST /nodes/{id}/hint``, and nothing called it. So ``needs_review`` was never entered,
``NodeSummaryRead.needs_practice`` was always ``false``, the "Para practicar" queue
``NodeList`` renders could never fill, and ``may_reprobe`` could never authorize anything.
``tests/test_mastery.py`` covered the pure rule; nothing covered the path that reaches it.

The three things asserted here are exactly the three the ladder promises:

1. **The third hint exhausts the quota.** Hints 1..3 escalate and are served; the fourth
   request is a ``409``, and the count of record is ``node_attempts.hints_used`` — never
   the number the client sends.
2. **The fourth failure after them lands in ``needs_review``**, with
   ``show_worked_solution: true`` and the answer revealed.
3. **That node then shows up in the practice queue** — ``GET /courses/{id}/nodes`` marks
   it ``needs_practice``, which is what puts it in the "Para practicar" section instead of
   letting it disappear.

No database and no network, same technique as ``tests/test_node_routes_authorization.py``:
the session dependency is a stub and the repositories the routes name are replaced with
in-memory doubles. The **rule itself is real** — ``transition_on_answer``, ``grade_item``
and ``may_offer_hint`` all run unpatched — so this is a test of the wiring, which is the
half that was missing.
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
from src.services.mastery_service import HINT_LIMIT

PREFIX = "/api/v1"

ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
COURSE_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
NODE_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
RENDER_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")

ITEM_ID = "q1"
#: Index 1 is right, so ``{"selected": 0}`` is a failure and ``{"selected": 1}`` is not.
CORRECT_OPTION = 1


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
    summary: str = "30 dias naturales desde la entrega."
    criticality: str = "recommended"
    position: int = 1
    archived: bool = False
    estimated_minutes: int | None = 6
    skill_id: uuid.UUID | None = None
    reviewed_at: Any = None
    mastery_threshold: float | None = None
    probe_items: list = field(default_factory=list)
    seed_lesson_id: uuid.UUID | None = None


def _ui_spec() -> dict:
    return {
        "components": [
            {
                "type": "QuizItem",
                "id": ITEM_ID,
                "props": {
                    "item_id": ITEM_ID,
                    "item_type": "test",
                    "bloom_level": "apply",
                    "question": "Un cliente vuelve a los 40 dias. Que aplicas?",
                    "options": [
                        "Aceptar la devolucion",
                        "Ofrecer garantia del fabricante",
                        "Rechazar sin mas",
                    ],
                },
            }
        ]
    }


@dataclass
class FakeRender:
    id: uuid.UUID = RENDER_ID
    node_id: uuid.UUID = NODE_ID
    org_id: uuid.UUID = ORG_ID
    ui_format: str = "exercise"
    status: NodeRenderStatus = NodeRenderStatus.READY
    backend: str = "openui"
    dialect: str = 'root = Stack([], "md")\n'
    ui_spec: dict = field(default_factory=_ui_spec)
    answer_key: dict = field(
        default_factory=lambda: {
            ITEM_ID: {
                "correct": CORRECT_OPTION,
                "explanation": "Pasados 30 dias la devolucion no aplica; queda la garantia.",
            }
        }
    )


@dataclass
class FakeAttempt:
    """One ``node_attempts`` row, reduced to the four columns the ladder reads."""

    item_id: str
    passed: bool
    hints_used: int = 0


class FakeState:
    """Enough of ``learner_node_states`` for ``apply_transition`` to write onto."""

    def __init__(self) -> None:
        self.user_id = USER_ID
        self.node_id = NODE_ID
        self.state = "learning"
        self.mastery = 0.4
        self.probe_score = 0.4
        self.consecutive_correct = 0
        self.consecutive_failed = 0
        self.hints_used = 0
        self.attempts_count = 0
        self.scaffold_band = "neutral"
        self.last_error_kind: str | None = None
        self.first_seen_at: Any = None
        self.mastered_at: Any = None
        self.updated_at: Any = None
        self.waived_by: uuid.UUID | None = None
        self.waived_at: Any = None
        self.active_render_id: uuid.UUID | None = None


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
    async def execute(self, _query: Any) -> FakeResult:
        return FakeResult([])

    async def get(self, _model: Any, _pk: Any) -> None:
        return None

    def add(self, _obj: Any) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


@dataclass
class World:
    node: FakeNode = field(default_factory=FakeNode)
    course: FakeCourse = field(default_factory=FakeCourse)
    render: FakeRender = field(default_factory=FakeRender)
    state: FakeState = field(default_factory=FakeState)
    attempts: list[FakeAttempt] = field(default_factory=list)


def _install(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
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
            node = world.node
            if node.id != node_id or node.org_id != org_id:
                return None
            return node

        async def list_for_course(self, _course_id: uuid.UUID, include_archived: bool = False):
            return [world.node]

        async def prerequisites_for(self, _node_ids):
            return {}

    class FakeEnrollmentRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_by_user_and_course(self, _user_id: uuid.UUID, _course_id: uuid.UUID):
            return object()

    class FakeRenderRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_scoped(self, render_id: uuid.UUID, org_id: uuid.UUID):
            render = world.render
            if render.id != render_id or render.org_id != org_id:
                return None
            return render

    class FakeAttemptRepo:
        """The in-memory half of ``node_attempts``, with the two queries that decide
        everything: ``MAX(hints_used)`` and ``COUNT(*) WHERE NOT passed``."""

        def __init__(self, _db: Any) -> None:
            pass

        def _rows(self, item_id: str) -> list[FakeAttempt]:
            return [row for row in world.attempts if row.item_id == item_id]

        async def count_for_item(self, *, user_id, node_id, item_id: str) -> int:
            return len(self._rows(item_id))

        async def count_failures_for_item(self, *, user_id, node_id, item_id: str) -> int:
            return len([row for row in self._rows(item_id) if not row.passed])

        async def hints_used_for_item(self, *, user_id, node_id, item_id: str) -> int:
            rows = self._rows(item_id)
            return max((row.hints_used for row in rows), default=0)

        async def latest_for_item(self, *, user_id, node_id, item_id: str):
            rows = self._rows(item_id)
            return rows[-1] if rows else None

        async def record(self, **kwargs: Any) -> FakeAttempt:
            row = FakeAttempt(
                item_id=kwargs["item_id"],
                passed=bool(kwargs["passed"]),
                hints_used=int(kwargs.get("hints_used") or 0),
            )
            world.attempts.append(row)
            return row

        async def update(self, row: FakeAttempt, **changes: Any) -> FakeAttempt:
            for name, value in changes.items():
                setattr(row, name, value)
            return row

    class FakeStateRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_by_user_and_node(self, _user_id, _node_id):
            return world.state

        async def get_or_create(self, *, user_id, node_id, mastery: float = 0.0):
            return world.state

        async def states_for_nodes(self, *, user_id, node_ids):
            return {world.state.node_id: world.state}

        async def unmastered_prerequisites(self, *, user_id, node_id):
            return []

        async def apply_transition(self, state: FakeState, transition, *, now=None):
            # The same writes the real repository performs, minus the timestamps.
            state.state = transition.to_state
            for column, value in transition.changes.items():
                setattr(state, column, value)
            state.attempts_count += transition.attempts_delta
            return state

    class NoProfileRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_by_user(self, _user_id):
            return None

    monkeypatch.setattr(nodes_routes, "CourseRepository", FakeCourseRepo)
    monkeypatch.setattr(nodes_routes, "CourseNodeRepository", FakeNodeRepo)
    monkeypatch.setattr(nodes_routes, "EnrollmentRepository", FakeEnrollmentRepo)
    monkeypatch.setattr(nodes_routes, "NodeRenderRepository", FakeRenderRepo)
    monkeypatch.setattr(nodes_routes, "NodeAttemptRepository", FakeAttemptRepo)
    monkeypatch.setattr(nodes_routes, "LearnerNodeStateRepository", FakeStateRepo)
    monkeypatch.setattr(nodes_routes, "LearnerProfileRepository", NoProfileRepo)
    monkeypatch.setattr(nodes_routes, "resolve_delivery", lambda *_a, **_k: "dynamic")


@pytest.fixture
def world() -> World:
    return World()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, world: World) -> TestClient:
    _install(monkeypatch, world)
    app = create_app()
    app.dependency_overrides[get_async_session] = lambda: StubSession()
    app.dependency_overrides[current_user] = lambda: FakeUser()
    return TestClient(app, raise_server_exceptions=False)


def ask_hint(client: TestClient) -> Any:
    return client.post(
        f"{PREFIX}/nodes/{NODE_ID}/hint",
        json={"render_id": str(RENDER_ID), "item_id": ITEM_ID},
    )


def answer(client: TestClient, *, selected: int, hints_used: int = 0) -> Any:
    return client.post(
        f"{PREFIX}/nodes/{NODE_ID}/answer",
        json={
            "render_id": str(RENDER_ID),
            "item_id": ITEM_ID,
            "answer": {"selected": selected},
            "hints_used": hints_used,
        },
    )


def fail(client: TestClient, **kwargs: Any) -> Any:
    return answer(client, selected=0, **kwargs)


# --------------------------------------------------------------------------------------
# 1. The quota
# --------------------------------------------------------------------------------------
def test_a_hint_needs_an_honest_try_first(client: TestClient, world: World) -> None:
    """``attempt-before-hint`` (§7.4). With no attempt recorded the hint is a ``409``, not
    a free first look at the item."""
    conflict = ask_hint(client)
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["field"] == "item_id"
    assert world.attempts == []


def test_three_hints_escalate_and_the_third_exhausts_the_quota(
    client: TestClient, world: World
) -> None:
    """The ladder of §7.4: node idea -> structural nudge -> the worked explanation. Each
    step is *different* — an escalation that repeats itself is not an escalation — and the
    count that stops it is the server's."""
    assert fail(client).status_code == 200

    hints = []
    for level in range(1, HINT_LIMIT + 1):
        response = ask_hint(client)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["hints_used"] == level
        assert body["hints_remaining"] == HINT_LIMIT - level
        hints.append(body["hint"])

    assert len(set(hints)) == HINT_LIMIT
    # 1 points back at the node, 2 rules distractors out, 3 is the key's explanation.
    assert world.node.summary in hints[0]
    assert "descartar" in hints[1]
    assert hints[2] == world.render.answer_key[ITEM_ID]["explanation"]

    spent = ask_hint(client)
    assert spent.status_code == 409, spent.text
    assert spent.json()["field"] == "hints_used"
    # The quota is stored, not counted in the request: it survived four requests.
    assert max(row.hints_used for row in world.attempts) == HINT_LIMIT


def test_answering_again_does_not_reset_the_quota(
    client: TestClient, world: World
) -> None:
    """A new ``node_attempts`` row inherits the hints already spent. Otherwise "retry"
    would be a quota reset button and the ladder would never end."""
    assert fail(client).status_code == 200
    for _ in range(HINT_LIMIT):
        assert ask_hint(client).status_code == 200

    assert fail(client).status_code == 200
    assert world.attempts[-1].hints_used == HINT_LIMIT
    assert ask_hint(client).status_code == 409


def test_the_client_cannot_buy_the_answer_with_its_own_hint_count(
    client: TestClient,
) -> None:
    """``NodeAnswerRequest.hints_used`` is informative. A browser posting ``3`` with no
    hint asked must not be handed ``correct_answer``."""
    body = fail(client, hints_used=99).json()
    assert body["correct_answer"] is None
    assert body["show_worked_solution"] is False


# --------------------------------------------------------------------------------------
# 2. The fourth failure
# --------------------------------------------------------------------------------------
def test_the_fourth_failure_after_three_hints_reaches_needs_review(
    client: TestClient, world: World
) -> None:
    """Rule 8 of §7.3, reached through the product for the first time.

    Three failures, three hints, and the fourth failure closes the item: the worked
    solution is shown, the key is revealed (withholding it now would be cruelty, not
    security — the third hint already gave the reasoning) and the node moves to
    ``needs_review`` instead of looping.
    """
    for _ in range(3):
        assert fail(client).status_code == 200
    for _ in range(HINT_LIMIT):
        assert ask_hint(client).status_code == 200

    final = fail(client)
    assert final.status_code == 200, final.text
    body = final.json()

    assert body["show_worked_solution"] is True
    assert body["state"] == "needs_review"
    assert body["correct_answer"] == {
        "correct": CORRECT_OPTION,
        "explanation": world.render.answer_key[ITEM_ID]["explanation"],
    }
    assert world.state.state == "needs_review"


def test_a_fourth_failure_without_hints_stays_in_learning(client: TestClient) -> None:
    """Both halves of the condition are required. Failing four times without ever asking
    for a hint is a hard item, not an exit: §7.4 wants the scaffolding *spent* before the
    node leaves the normal flow."""
    for _ in range(3):
        assert fail(client).status_code == 200
    body = fail(client).json()
    assert body["state"] == "learning"
    assert body["show_worked_solution"] is False


# --------------------------------------------------------------------------------------
# 3. The practice queue
# --------------------------------------------------------------------------------------
def test_the_node_then_appears_in_the_practice_queue(
    client: TestClient, world: World
) -> None:
    """The other end of the wire: ``NodeList`` renders a "Para practicar" section from
    ``needs_practice``, and until the ladder existed that flag could never be ``true``."""
    for _ in range(3):
        assert fail(client).status_code == 200
    for _ in range(HINT_LIMIT):
        assert ask_hint(client).status_code == 200
    assert fail(client).json()["state"] == "needs_review"

    listing = client.get(f"{PREFIX}/courses/{COURSE_ID}/nodes")
    assert listing.status_code == 200, listing.text
    rows = listing.json()["nodes"]
    assert [row["id"] for row in rows] == [str(NODE_ID)]
    assert rows[0]["state"] == "needs_review"
    assert rows[0]["needs_practice"] is True
