"""The two ways out of a Didact activity that the learner takes on purpose.

Until these routes existed the only exit was to fail the same activity four times and be
handed the solution — help you get by running out, not by asking. Both new endpoints hang
off the one piece that was missing, ``learner_activity_states``: a server-owned counter per
``(user, activity)``.

What is pinned here:

1. **``POST /activities/{id}/hint`` counts per activity.** Attempt-before-hint, a hard cap
   of three, and the count is the server's — a ``hints_used`` in the request body is
   ignored. Spending the quota on one activity leaves the next one's quota untouched,
   which is the whole reason the counter is not the node's.
2. **``POST /activities/{id}/solution`` is remembered.** It requires an attempt, it answers
   with the same shape ``result.solution`` already travels in (or ``null`` when the mode
   cannot be written out), and it leaves ``solution_revealed_at`` behind — so the reveal
   survives the request that produced it instead of living in the browser's component
   state until the next reload.
3. **Neither one fabricates mastery.** The learner-node repository is a tripwire in this
   file: asking for help is not evidence about anybody, so nothing on these paths may
   reach ``learner_node_states``.

No database and no network, the technique of ``tests/test_activity_evaluate_mastery.py``:
the session dependency is a stub and the repositories the route names are in-memory
doubles. The rules themselves run unpatched — ``may_offer_hint``, ``activity_hint`` and
``render_solution`` are the real ones.
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
from src.models import UserRole
from src.models.activity_definition import ActivityFamily
from src.routes import activities as activity_routes
from src.services.activity_hints import activity_hint
from src.services.mastery_service import HINT_LIMIT

PREFIX = "/api/v1"

ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
COURSE_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
NODE_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
ACTIVITY_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")
ACTIVITY_B_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")

SUMMARY = "El plazo de devolucion es de 30 dias naturales desde la entrega."
EXPLANATION = "La fuente lo dice en el segundo parrafo."


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
class FakeNode:
    id: uuid.UUID = NODE_ID
    org_id: uuid.UUID = ORG_ID
    course_id: uuid.UUID = COURSE_ID
    summary: str = SUMMARY
    archived: bool = False


def _public() -> dict:
    return {
        "question": "¿Cuando caduca el plazo?",
        "options": [
            {"value": "a", "label": "A los 30 dias"},
            {"value": "b", "label": "A los 7 dias"},
            {"value": "c", "label": "Nunca caduca"},
        ],
    }


def _private() -> dict:
    return {"evaluation": {"mode": "exact", "expected": "a", "explanation": EXPLANATION}}


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
    private_definition: dict = field(default_factory=_private)
    required_ports: list = field(default_factory=lambda: ["evaluation"])
    provenance: dict = field(default_factory=dict)


@dataclass
class FakeCounters:
    """One ``learner_activity_states`` row."""

    attempts_count: int = 0
    failures_count: int = 0
    hints_used: int = 0
    solution_revealed_at: Any = None


class StubSession:
    commits = 0

    async def commit(self) -> None:
        type(self).commits += 1

    async def flush(self) -> None:
        return None

    def add(self, _obj: Any) -> None:
        return None


@dataclass
class World:
    node: FakeNode | None = field(default_factory=FakeNode)
    activity: FakeActivity = field(default_factory=FakeActivity)
    other_activity: FakeActivity = field(
        default_factory=lambda: FakeActivity(id=ACTIVITY_B_ID)
    )
    counters: dict[uuid.UUID, FakeCounters] = field(default_factory=dict)

    def tried(self, activity_id: uuid.UUID = ACTIVITY_ID, *, times: int = 1) -> FakeCounters:
        """Seed the counter the way a graded submission would leave it.

        Deliberately not routed through ``/evaluate``: these two endpoints must not need
        the mastery machinery to be reachable, and the tripwire below proves they do not
        touch it.
        """
        row = self.counters.setdefault(activity_id, FakeCounters())
        row.attempts_count += times
        row.failures_count += times
        return row


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
        """The client-owned blob. Empty here: this file is about the server's counters,
        and the only reason the route reads it at all is to hand it back untouched.
        """

        def __init__(self, _db: Any) -> None:
            pass

        async def get_for_learner(self, _activity_id, _user_id):
            return None

    class FakeNodeRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_scoped(self, node_id: uuid.UUID, org_id: uuid.UUID):
            node = world.node
            if node is None or node.id != node_id or node.org_id != org_id:
                return None
            return node

    class FakeCounterRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def get_for_learner(self, activity_id: uuid.UUID, _user_id: uuid.UUID):
            return world.counters.get(activity_id)

        async def get_or_create(self, *, activity: FakeActivity, user_id: uuid.UUID):
            return world.counters.setdefault(activity.id, FakeCounters())

        async def record_hint(self, *, activity: FakeActivity, user_id, level: int):
            row = await self.get_or_create(activity=activity, user_id=user_id)
            row.hints_used = max(row.hints_used, level)
            return row

        async def mark_solution_revealed(self, *, activity: FakeActivity, user_id, now=None):
            row = await self.get_or_create(activity=activity, user_id=user_id)
            if row.solution_revealed_at is None:
                row.solution_revealed_at = now or "stamped"
            return row

    class TripwireStateRepo:
        """``learner_node_states`` is out of bounds on these two paths."""

        def __init__(self, _db: Any) -> None:
            raise AssertionError("asking for help must not reach learner_node_states")

    monkeypatch.setattr(activity_routes, "ActivityDefinitionRepository", FakeActivityRepo)
    monkeypatch.setattr(activity_routes, "ActivityStateRepository", FakeActivityStateRepo)
    monkeypatch.setattr(activity_routes, "CourseNodeRepository", FakeNodeRepo)
    monkeypatch.setattr(
        activity_routes, "LearnerActivityStateRepository", FakeCounterRepo
    )
    monkeypatch.setattr(activity_routes, "LearnerNodeStateRepository", TripwireStateRepo)


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


def hint(client: TestClient, activity_id: uuid.UUID = ACTIVITY_ID, body: dict | None = None):
    return client.post(f"{PREFIX}/activities/{activity_id}/hint", json=body or {})


def solution(client: TestClient, activity_id: uuid.UUID = ACTIVITY_ID):
    return client.post(f"{PREFIX}/activities/{activity_id}/solution", json={})


# --------------------------------------------------------------------------------------
# 1. The ladder
# --------------------------------------------------------------------------------------
def test_a_hint_is_refused_until_the_learner_has_tried(client: TestClient, world: World) -> None:
    """Attempt-before-hint (§7.4): a hint follows an honest try, or it is not a hint."""
    response = hint(client)

    assert response.status_code == 409
    assert response.json()["detail"] == "Inténtalo una vez antes de pedir una pista."
    assert ACTIVITY_ID not in world.counters


def test_the_three_hints_escalate_and_the_fourth_is_refused(
    client: TestClient, world: World
) -> None:
    world.tried()

    first = hint(client).json()
    assert first == {
        "hint": f"Vuelve a la idea del nodo: {SUMMARY}",
        "hints_used": 1,
        "hints_remaining": 2,
    }

    second = hint(client).json()
    # Rung 2 narrows the search without closing it: two distractors, never the answer.
    assert second["hint"] == 'Puedes descartar "A los 7 dias" y "Nunca caduca".'
    assert second["hints_remaining"] == 1
    assert "A los 30 dias" not in second["hint"]

    third = hint(client).json()
    assert third == {"hint": EXPLANATION, "hints_used": HINT_LIMIT, "hints_remaining": 0}

    spent = hint(client)
    assert spent.status_code == 409
    assert spent.json()["detail"] == "Ya has usado las tres pistas de esta actividad."
    assert world.counters[ACTIVITY_ID].hints_used == HINT_LIMIT


def test_the_count_is_the_servers_and_the_body_is_ignored(
    client: TestClient, world: World
) -> None:
    """A browser that fills in ``hints_used: 3`` would otherwise be asking for rung 3."""
    world.tried()

    response = hint(client, body={"hints_used": 3})

    assert response.status_code == 200
    assert response.json()["hints_used"] == 1
    assert world.counters[ACTIVITY_ID].hints_used == 1


def test_hints_are_counted_per_activity_not_per_node(
    client: TestClient, world: World
) -> None:
    """Symptom 2, as a test.

    The count used to be ``learner_node_states.hints_used``, one number for the whole
    node. Reading it here meant "te quedan N pistas" was reporting on something else
    entirely — and, had this route written to it, three hints spent on one activity would
    have emptied the quota of every other activity in the node.
    """
    world.tried()
    world.tried(ACTIVITY_B_ID)

    for _ in range(HINT_LIMIT):
        assert hint(client).status_code == 200
    assert hint(client).status_code == 409

    fresh = hint(client, ACTIVITY_B_ID).json()

    assert fresh["hints_used"] == 1
    assert fresh["hints_remaining"] == HINT_LIMIT - 1
    assert world.counters[ACTIVITY_ID].hints_used == HINT_LIMIT
    assert world.counters[ACTIVITY_B_ID].hints_used == 1


def test_a_missing_node_still_gets_a_first_hint(client: TestClient, world: World) -> None:
    """An archived node still has activities, and a learner in front of one is stuck."""
    world.node = None
    world.tried()

    body = hint(client).json()

    assert body["hint"] and "None" not in body["hint"]
    assert body["hints_used"] == 1


# --------------------------------------------------------------------------------------
# 2. The way out, on the record
# --------------------------------------------------------------------------------------
def test_the_solution_is_refused_until_the_learner_has_tried(
    client: TestClient, world: World
) -> None:
    response = solution(client)

    assert response.status_code == 409
    assert response.json()["detail"] == "Inténtalo una vez antes de ver la solución."
    assert ACTIVITY_ID not in world.counters


def test_the_solution_is_written_out_and_the_reveal_is_recorded(
    client: TestClient, world: World
) -> None:
    world.tried()

    response = solution(client)

    assert response.status_code == 200
    assert response.json() == {"solution": "A los 30 dias", "explanation": EXPLANATION}
    assert world.counters[ACTIVITY_ID].solution_revealed_at is not None


def test_a_revealed_solution_is_remembered_between_requests(
    client: TestClient, world: World
) -> None:
    """Symptom 3, as a test.

    The reveal used to live only in the component's own state, so a reload reopened an
    activity the learner had already closed. The stamp is the record, and a second request
    is the same reveal — not a new one.
    """
    world.tried()

    first = solution(client)
    stamped_at = world.counters[ACTIVITY_ID].solution_revealed_at
    world.counters[ACTIVITY_ID].solution_revealed_at = stamped_at  # unchanged below
    second = solution(client)

    assert stamped_at is not None
    assert second.status_code == 200
    assert second.json() == first.json()
    # Never moved: the question the column answers is "was this opened", and it was.
    assert world.counters[ACTIVITY_ID].solution_revealed_at is stamped_at


def test_revealing_one_solution_leaves_the_next_activity_closed(
    client: TestClient, world: World
) -> None:
    world.tried()
    world.tried(ACTIVITY_B_ID)

    assert solution(client).status_code == 200

    assert world.counters[ACTIVITY_B_ID].solution_revealed_at is None


def test_an_unwritable_mode_answers_nothing_and_still_records_the_reveal(
    client: TestClient, world: World
) -> None:
    """``null`` is an answer: asked, nothing to print, and the learner still gets out."""
    world.activity.private_definition = {"evaluation": {"mode": "llm_rubric"}}
    world.tried()

    response = solution(client)

    assert response.status_code == 200
    assert response.json() is None
    assert world.counters[ACTIVITY_ID].solution_revealed_at is not None


def test_asking_for_the_answer_never_moves_a_counter_that_measures(
    client: TestClient, world: World
) -> None:
    """Being shown the answer demonstrates nothing, so nothing that scores may move.

    The learner-node repository is a tripwire in this file — reaching mastery from here
    would raise — and the activity's own numbers must not move either: a reveal is not an
    attempt and it is not a failure.
    """
    world.tried()

    assert hint(client).status_code == 200
    assert solution(client).status_code == 200

    row = world.counters[ACTIVITY_ID]
    assert (row.attempts_count, row.failures_count) == (1, 1)


def test_a_revealed_solution_survives_a_reload(client: TestClient, world: World) -> None:
    """The stamp is worth nothing if no read the client makes ever mentions it.

    Before this, closure lived only in component memory: reloading showed the activity
    open again, ready to be answered by somebody who had already been given the answer.
    The flag rides on `GET /activities/{id}/state` — next to the client-owned blob and
    not inside it, so writing state back cannot un-reveal a solution.
    """
    world.tried()

    before = client.get(f"{PREFIX}/activities/{ACTIVITY_ID}/state")
    assert before.status_code == 200
    assert before.json()["solution_revealed"] is False

    assert solution(client).status_code == 200

    after = client.get(f"{PREFIX}/activities/{ACTIVITY_ID}/state")
    assert after.json()["solution_revealed"] is True

# --------------------------------------------------------------------------------------
# 3. The ladder itself, without HTTP
# --------------------------------------------------------------------------------------
def test_rung_two_names_the_first_step_of_a_sequence() -> None:
    text = activity_hint(
        2,
        component_id="didact.sort",
        public_definition={
            "items": [
                {"id": "s1", "content": "Registrar la entrada"},
                {"id": "s2", "content": "Comprobar el albaran"},
            ]
        },
        evaluation={"mode": "sequence", "expected": ["s2", "s1"]},
        node_summary=SUMMARY,
    )

    assert text == 'El primer paso es "Comprobar el albaran".'


def test_rung_two_never_names_a_pair_of_an_assignment() -> None:
    """A sequence can spare its first element; an assignment cannot spare a whole pair."""
    text = activity_hint(
        2,
        component_id="didact.matching",
        public_definition={
            "sources": [{"id": "p1", "content": "Devolucion"}],
            "targets": [{"id": "t1", "content": "30 dias"}],
        },
        evaluation={"mode": "assignments", "expected": {"p1": "t1"}},
        node_summary=SUMMARY,
    )

    assert "Devolucion" in text
    assert "30 dias" not in text


def test_rung_two_gives_the_shape_of_a_written_answer() -> None:
    text = activity_hint(
        2,
        component_id="didact.quiz.short-answer",
        public_definition={},
        evaluation={"mode": "normalized_any", "expected": ["albaran", "albarán"]},
        node_summary=SUMMARY,
    )

    assert text == "Lo que falta: 7 caracteres, empieza por 'a'."


def test_a_mode_the_ladder_cannot_read_still_earns_a_sentence() -> None:
    """The quota is spent either way, so silence would be taking something for nothing."""
    text = activity_hint(
        2,
        component_id="didact.quiz.true-false",
        public_definition={"question": "¿Caduca a los 30 dias?"},
        evaluation={"mode": "exact", "expected": True},
        node_summary=SUMMARY,
    )

    assert text.strip()
    assert "True" not in text and "Verdadero" not in text
