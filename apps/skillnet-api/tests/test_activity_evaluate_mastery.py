"""``POST /activities/{id}/evaluate`` over HTTP: the verdict is now kept.

The endpoint used to score a submission and throw the result away — no attempt row, no
mastery, no ``db.commit()``. That was invisible on artifact-shaped activities and fatal on
the ones that matter: the default closer of a node is a Didact activity authored at
runtime, materialized **without** an ``ImplementationBinding``, so the client cannot use
``/attempts`` and posts here. The node's main check was graded and discarded, which meant
no failure was ever counted and no exit rule could fire.

Three things are pinned here, and the first is the reason the work was done:

1. **Four failures without a single hint open the exit.** ``show_worked_solution: true``
   and a readable solution. Didact closers have no hint ladder at all, so a rule 8 that
   demanded spent hints was a door with no handle on this side.
2. **Only the ``assessment`` family touches mastery.** An artifact activity gets the old,
   stateless answer, because it measures nobody.
3. **A repeated ``attempt_id`` replays instead of re-grading**, and a *different*
   submission under the same id is a ``409``.
4. **Failures are counted per activity**, from ``learner_activity_states``. They used to
   be counted per *node* — a deviation the route stated out loud in a comment — so three
   failures on one activity plus one on the next handed the second one's answer over.

No database and no network: the session dependency is a stub and the repositories the route
names are replaced with in-memory doubles, the technique of ``tests/test_hint_ladder.py``.
The rule itself is real — ``transition_on_answer``, ``MasteryEvidenceService.apply`` and the
built-in scorer all run unpatched.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.deps.auth import current_user
from src.deps.db import get_async_session
from src.main import create_app
from src.models import UserRole
from src.models.activity_definition import ActivityFamily
from src.routes import activities as activity_routes
from src.services.mastery_service import WORKED_SOLUTION_FAILURES

PREFIX = "/api/v1"

ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
COURSE_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
NODE_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
ACTIVITY_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")
#: A second activity of the **same node**, which is the whole point of it: rule 8 is per
#: question, so what happens in front of one must not open the other.
ACTIVITY_B_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")

RIGHT = "a"
WRONG = "b"


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
    delivery_mode: str = "dynamic"
    schema_status: str = "validated"


@dataclass
class FakeNode:
    id: uuid.UUID = NODE_ID
    org_id: uuid.UUID = ORG_ID
    course_id: uuid.UUID = COURSE_ID
    criticality: str = "recommended"
    archived: bool = False
    skill_id: uuid.UUID | None = None
    mastery_threshold: float | None = None


def _public() -> dict:
    return {
        "question": "¿Cuál es la respuesta documentada?",
        "options": [{"value": RIGHT, "label": "Opción A"}, {"value": WRONG, "label": "Opción B"}],
        "feedback": {"positive": "Eso es.", "negative": "Vuelve a la fuente."},
    }


@dataclass
class FakeActivity:
    id: uuid.UUID = ACTIVITY_ID
    org_id: uuid.UUID = ORG_ID
    course_id: uuid.UUID = COURSE_ID
    node_id: uuid.UUID = NODE_ID
    component_id: str = "didact.quiz.single-choice"
    family: ActivityFamily = ActivityFamily.ASSESSMENT
    version: int = 1
    enabled: bool = True
    public_definition: dict = field(default_factory=_public)
    private_definition: dict = field(
        default_factory=lambda: {
            "evaluation": {
                "mode": "exact",
                "expected": RIGHT,
                "explanation": "La fuente lo dice en el segundo párrafo.",
            }
        }
    )
    required_ports: list = field(default_factory=lambda: ["evaluation"])
    provenance: dict = field(default_factory=dict)


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
        self.mastered_at: Any = None


@dataclass
class FakeCounters:
    """One ``learner_activity_states`` row: what this learner spent on one activity."""

    attempts_count: int = 0
    failures_count: int = 0
    hints_used: int = 0
    solution_revealed_at: Any = None


@dataclass
class FakeEvent:
    """One ``learning_events`` row, reduced to what the replay path reads."""

    id: uuid.UUID
    user_id: uuid.UUID
    node_id: uuid.UUID
    type: str
    event_metadata: dict


class FakeResult:
    def scalar_one_or_none(self) -> None:
        return None

    def scalars(self) -> FakeResult:
        return self

    def all(self) -> list[Any]:
        return []

    def first(self) -> None:
        return None


class StubSession:
    async def execute(self, _query: Any) -> FakeResult:
        return FakeResult()

    async def get(self, _model: Any, _pk: Any) -> None:
        return None

    def add(self, _obj: Any) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        return None

    commits = 0


@dataclass
class World:
    node: FakeNode = field(default_factory=FakeNode)
    course: FakeCourse = field(default_factory=FakeCourse)
    activity: FakeActivity = field(default_factory=FakeActivity)
    other_activity: FakeActivity = field(
        default_factory=lambda: FakeActivity(id=ACTIVITY_B_ID)
    )
    state: FakeState = field(default_factory=FakeState)
    counters: dict[uuid.UUID, FakeCounters] = field(default_factory=dict)
    events: dict[uuid.UUID, FakeEvent] = field(default_factory=dict)
    transitions: list[int] = field(default_factory=list)


def _install(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    class FakeActivityRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_scoped(self, activity_id: uuid.UUID, org_id: uuid.UUID):
            for activity in (world.activity, world.other_activity):
                if activity.id == activity_id and activity.org_id == org_id:
                    return activity
            return None

    class FakeActivityStateRepo:
        def __init__(self, _db: Any) -> None:
            pass

    class FakeCounterRepo:
        """``learner_activity_states``, keyed by activity exactly as the real one is."""

        def __init__(self, _db: Any) -> None:
            pass

        async def get_for_learner(self, activity_id: uuid.UUID, _user_id: uuid.UUID):
            return world.counters.get(activity_id)

        async def get_or_create(self, *, activity: FakeActivity, user_id: uuid.UUID):
            return world.counters.setdefault(activity.id, FakeCounters())

        async def record_attempt(self, *, activity: FakeActivity, user_id, passed: bool):
            row = await self.get_or_create(activity=activity, user_id=user_id)
            row.attempts_count += 1
            if not passed:
                row.failures_count += 1
            return row

    class FakeCourseRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_scoped(self, course_id: uuid.UUID, org_id: uuid.UUID):
            course = world.course
            if course.id != course_id or course.org_id != org_id:
                return None
            return course

    class FakeNodeRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_scoped(self, node_id: uuid.UUID, org_id: uuid.UUID):
            node = world.node
            if node.id != node_id or node.org_id != org_id:
                return None
            return node

    class FakeStateRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_by_user_and_node(self, _user_id, _node_id):
            return world.state

        async def get_or_create(self, *, user_id, node_id, mastery: float = 0.0):
            return world.state

        async def unmastered_prerequisites(self, *, user_id, node_id):
            return []

        async def apply_transition(self, state: FakeState, transition, *, now=None):
            world.transitions.append(transition.rule)
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

    class FakeEventRepo:
        """``learning_events`` keyed by the client's ``attempt_id``, first write wins."""

        def __init__(self, _db: Any) -> None:
            pass

        async def get_by_id(self, event_id: uuid.UUID):
            return world.events.get(event_id)

        async def record_didact_event(
            self, *, event_id, user_id, node_id, event_type, metadata
        ) -> bool:
            if event_id in world.events:
                return False
            world.events[event_id] = FakeEvent(
                id=event_id,
                user_id=user_id,
                node_id=node_id,
                type=f"didact.{event_type}",
                event_metadata=dict(metadata),
            )
            return True

    monkeypatch.setattr(activity_routes, "ActivityDefinitionRepository", FakeActivityRepo)
    monkeypatch.setattr(activity_routes, "ActivityStateRepository", FakeActivityStateRepo)
    monkeypatch.setattr(activity_routes, "CourseRepository", FakeCourseRepo)
    monkeypatch.setattr(activity_routes, "CourseNodeRepository", FakeNodeRepo)
    monkeypatch.setattr(activity_routes, "LearnerNodeStateRepository", FakeStateRepo)
    monkeypatch.setattr(
        activity_routes, "LearnerActivityStateRepository", FakeCounterRepo
    )
    monkeypatch.setattr(activity_routes, "LearnerProfileRepository", NoProfileRepo)
    monkeypatch.setattr(activity_routes, "LearningEventRepository", FakeEventRepo)


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


def evaluate(
    client: TestClient,
    *,
    answer: str = WRONG,
    attempt_id: uuid.UUID | None = None,
    activity_id: uuid.UUID = ACTIVITY_ID,
):
    body: dict[str, Any] = {"submission": {"answer": answer}}
    if attempt_id is not None:
        body["attempt_id"] = str(attempt_id)
    return client.post(f"{PREFIX}/activities/{activity_id}/evaluate", json=body)


# --------------------------------------------------------------------------------------
# 1. The verdict counts
# --------------------------------------------------------------------------------------
def test_a_failure_moves_the_learner_state(client: TestClient, world: World) -> None:
    """The bug in one assertion: before this, nothing below changed."""
    response = evaluate(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert body["result"]["outcome"] == "incorrect"
    assert body["result"]["feedback"] == "Vuelve a la fuente."
    assert world.state.consecutive_failed == 1
    assert world.state.attempts_count == 1
    assert body["result"]["state"] == world.state.state
    assert body["result"]["mastery"] == pytest.approx(world.state.mastery)


def test_four_failures_without_a_single_hint_open_the_exit(
    client: TestClient, world: World
) -> None:
    """**The headline.** Four failures, zero hints asked, and the learner is let out.

    A Didact closer has no hint ladder — there is no ``POST /hint`` behind it and
    ``learner_node_states.hints_used`` stays at zero for its whole life. While rule 8 also
    demanded ``hints_used >= HINT_LIMIT`` this exit was unreachable by construction, so the
    node's own test was a wall. The failures are the evidence now, and the worked solution
    comes with them.
    """
    for _ in range(WORKED_SOLUTION_FAILURES - 1):
        interim = evaluate(client).json()
        assert interim["result"]["show_worked_solution"] is False

    body = evaluate(client).json()

    assert world.state.hints_used == 0
    assert world.transitions[-1] == 8
    assert body["result"]["show_worked_solution"] is True
    assert body["result"]["solution"] == {
        "solution": "Opción A",
        "explanation": "La fuente lo dice en el segundo párrafo.",
    }
    # `learning`, never `mastered`: being shown the answer demonstrates nothing.
    assert body["result"]["state"] == "learning"


def test_failing_one_activity_does_not_open_another_in_the_same_node(
    client: TestClient, world: World
) -> None:
    """The deviation, as a test: rule 8 is per question and this is what that means.

    Three failures on activity A, then a *first* failure on activity B of the same node.
    While ``item_failures`` came from ``learner_node_states.consecutive_failed`` the node's
    streak was 4 by then, so B — which the learner had missed exactly once — handed over
    its own answer. The counter is B's own now, and B is still a question.
    """
    for _ in range(WORKED_SOLUTION_FAILURES - 1):
        evaluate(client)

    body = evaluate(client, activity_id=ACTIVITY_B_ID).json()

    assert body["result"]["show_worked_solution"] is False
    assert body["result"]["solution"] is None
    assert world.transitions[-1] != 8
    assert world.counters[ACTIVITY_ID].failures_count == 3
    assert world.counters[ACTIVITY_B_ID].failures_count == 1
    # And nothing was taken away from A: its own fourth failure still opens it.
    assert evaluate(client).json()["result"]["show_worked_solution"] is True


def test_a_correct_answer_raises_mastery(client: TestClient, world: World) -> None:
    before = world.state.mastery
    body = evaluate(client, answer=RIGHT).json()

    assert body["result"]["passed"] is True
    assert body["result"]["mastery"] > before
    assert world.state.consecutive_correct == 1
    # Passing reveals the key, the same rule ``POST /nodes/{id}/answer`` applies.
    assert body["result"]["solution"] == {
        "solution": "Opción A",
        "explanation": "La fuente lo dice en el segundo párrafo.",
    }


def test_the_key_is_not_handed_over_on_an_ordinary_failure(client: TestClient) -> None:
    body = evaluate(client).json()
    assert body["result"]["show_worked_solution"] is False
    assert body["result"]["solution"] is None
    assert "expected" not in str(body)


# --------------------------------------------------------------------------------------
# 2. Only the assessment family
# --------------------------------------------------------------------------------------
def test_an_artifact_activity_never_touches_mastery(client: TestClient, world: World) -> None:
    """An artifact is not a measurement of anyone, so it must not move a certificate."""
    world.activity.family = ActivityFamily.ARTIFACT

    body = evaluate(client).json()

    assert body["status"] == "completed"
    assert world.transitions == []
    assert world.state.consecutive_failed == 0
    # And the old contract is untouched: no learner-scoped fields appear at all.
    assert set(body["result"]) == {"outcome", "passed", "score", "feedback"}


# --------------------------------------------------------------------------------------
# 3. Idempotency
# --------------------------------------------------------------------------------------
def test_a_repeated_attempt_id_replays_instead_of_grading_again(
    client: TestClient, world: World
) -> None:
    """A double click must not count two failures against the same submission."""
    attempt_id = uuid.uuid4()
    first = evaluate(client, attempt_id=attempt_id)
    second = evaluate(client, attempt_id=attempt_id)

    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
    assert world.transitions == [0]
    assert world.state.consecutive_failed == 1


def test_reusing_an_attempt_id_for_another_submission_is_a_conflict(
    client: TestClient, world: World
) -> None:
    attempt_id = uuid.uuid4()
    assert evaluate(client, attempt_id=attempt_id).status_code == 200
    clash = evaluate(client, answer=RIGHT, attempt_id=attempt_id)

    assert clash.status_code == 409
    assert world.transitions == [0]


def test_without_an_attempt_id_each_submission_is_graded(
    client: TestClient, world: World
) -> None:
    """The field is optional and additive: an older client keeps its old behaviour."""
    assert evaluate(client).status_code == 200
    assert evaluate(client).status_code == 200
    assert world.state.consecutive_failed == 2
    assert world.events == {}


# --------------------------------------------------------------------------------------
# 4. The broken activity
# --------------------------------------------------------------------------------------
def test_an_unevaluable_activity_lets_the_learner_through_immediately(
    client: TestClient, world: World, caplog: pytest.LogCaptureFixture
) -> None:
    """The third dead end: a key that cannot grade produces no countable failure either.

    Without its own branch the learner would submit into a decline for ever — rule 8 needs
    failures to count, and nothing here ever counts one. So the response says the activity
    is broken and hands the client ``show_worked_solution`` on the first submission.
    """
    world.activity.private_definition = {}

    with caplog.at_level(logging.WARNING):
        body = evaluate(client).json()

    assert body["status"] == "declined"
    assert body["decline_reason"] == "missing_evaluation_definition"
    assert body["result"]["show_worked_solution"] is True
    assert body["result"]["solution"] is None
    assert world.transitions == []
    # The defect is a generation bug, and it was invisible until now.
    assert "missing_evaluation_definition" in caplog.text
    assert str(ACTIVITY_ID) in caplog.text


def test_an_unsupported_mode_is_reported_the_same_way(
    client: TestClient, world: World, caplog: pytest.LogCaptureFixture
) -> None:
    world.activity.private_definition = {"evaluation": {"mode": "llm_rubric", "expected": RIGHT}}

    with caplog.at_level(logging.WARNING):
        body = evaluate(client).json()

    assert body["decline_reason"] == "unsupported_evaluation_mode"
    assert body["result"]["show_worked_solution"] is True


def test_a_port_decline_keeps_the_plain_shape(client: TestClient, world: World) -> None:
    """A disabled activity is already reported by ``GET /definition``; nobody is stuck."""
    world.activity.enabled = False

    body = evaluate(client).json()

    assert body["status"] == "declined"
    assert body["decline_reason"] == "activity_disabled"
    assert body["result"] is None
