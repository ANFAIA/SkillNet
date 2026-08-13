import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError as PydanticValidationError

from src.repositories.learning_event_repo import LearningEventRepository
from src.routes import activities
from src.schemas.activity import DidactEventEnvelope


def envelope(**overrides) -> DidactEventEnvelope:
    values = {
        "version": 1,
        "event_id": uuid.uuid4(),
        "activity_id": uuid.uuid4(),
        "component_id": "didact.measurement-lab",
        "type": "started",
        "occurred_at": datetime.now(timezone.utc),
        "payload": {},
    }
    values.update(overrides)
    return DidactEventEnvelope(**values)


@pytest.mark.parametrize(
    "payload",
    [
        {"answer": "private learner response"},
        {"solution": "private server solution"},
        {"response": {"free_text": "not telemetry"}},
    ],
)
def test_event_envelope_rejects_private_or_free_form_payload(payload):
    with pytest.raises(PydanticValidationError):
        envelope(payload=payload)


def test_event_envelope_is_closed_and_versioned():
    with pytest.raises(PydanticValidationError):
        envelope(version=2)
    with pytest.raises(PydanticValidationError):
        envelope(type="invented")
    with pytest.raises(PydanticValidationError):
        envelope(extra_private_field=True)
    with pytest.raises(PydanticValidationError):
        envelope(type="mastered")


class StubSession:
    def __init__(self):
        self.statement = None
        self.commits = 0

    async def execute(self, statement):
        self.statement = statement
        return SimpleNamespace(rowcount=1)

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_repository_uses_event_id_idempotently_and_zero_weight():
    session = StubSession()
    event_id = uuid.uuid4()

    inserted = await LearningEventRepository(session).record_didact_event(
        event_id=event_id,
        user_id=uuid.uuid4(),
        node_id=uuid.uuid4(),
        event_type="completed",
        metadata={"schema_version": 1},
    )

    assert inserted is True
    compiled = session.statement.compile()
    assert "ON CONFLICT (id) DO NOTHING" in str(compiled)
    assert compiled.params["id"] == event_id
    assert compiled.params["type"] == "didact.completed"
    assert compiled.params["weight"] == 0.0
    assert compiled.params["element"] is None


@pytest.mark.parametrize(
    "event_type",
    ["started", "attempted", "answered", "feedback_viewed", "completed"],
)
def test_didact_event_types_have_zero_personalization_weight(event_type):
    from src.services.learner_profile_service import weight_for

    assert weight_for(f"didact.{event_type}") == 0.0


@pytest.mark.asyncio
async def test_didact_events_are_excluded_from_format_vector_samples():
    class Result:
        def all(self):
            return []

    class Session:
        async def execute(self, statement):
            self.statement = statement
            return Result()

    session = Session()
    await LearningEventRepository(session).window_samples(
        user_id=uuid.uuid4(),
        since=datetime.now(timezone.utc),
    )

    compiled = session.statement.compile()
    assert "learning_events.type NOT LIKE" in str(compiled)
    assert "didact." in compiled.params.values()


@pytest.mark.asyncio
async def test_didact_events_are_excluded_from_recent_personalization_signals():
    class ScalarResult:
        def all(self):
            return []

    class Result:
        def scalars(self):
            return ScalarResult()

    class Session:
        async def execute(self, statement):
            self.statement = statement
            return Result()

    session = Session()
    await LearningEventRepository(session).recent_types_for_node(
        user_id=uuid.uuid4(),
        node_id=uuid.uuid4(),
    )

    compiled = str(session.statement.compile())
    assert "learning_events.type NOT LIKE" in compiled
    assert "didact." in session.statement.compile().params.values()


@pytest.mark.asyncio
async def test_activity_event_resolves_server_scope_and_coordinates(monkeypatch):
    activity_id = uuid.uuid4()
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    node_id = uuid.uuid4()
    body = envelope(activity_id=activity_id)
    activity = SimpleNamespace(
        id=activity_id,
        org_id=org_id,
        node_id=node_id,
        component_id=body.component_id,
    )
    seen = {}

    class Service:
        async def get(self, requested_activity_id, requested_org_id):
            seen["scope"] = (requested_activity_id, requested_org_id)
            return activity

    class Events:
        def __init__(self, session):
            seen["session"] = session

        async def record_didact_event(self, **values):
            seen["event"] = values
            return True

    session = StubSession()
    monkeypatch.setattr(activities, "_service", lambda _db: Service())
    monkeypatch.setattr(activities, "LearningEventRepository", Events)

    response = await activities.record_activity_event(
        SimpleNamespace(id=user_id, org_id=org_id),
        session,
        activity_id,
        body,
    )

    assert response.status_code == 204
    assert seen["scope"] == (activity_id, org_id)
    assert seen["event"]["user_id"] == user_id
    assert seen["event"]["node_id"] == node_id
    assert seen["event"]["metadata"]["activity_id"] == str(activity_id)
    assert seen["event"]["metadata"]["component_id"] == body.component_id
    assert session.commits == 1


@pytest.mark.asyncio
async def test_activity_event_rejects_component_spoofing(monkeypatch):
    activity_id = uuid.uuid4()
    body = envelope(activity_id=activity_id, component_id="didact.evidence-annotation")
    activity = SimpleNamespace(
        id=activity_id,
        node_id=uuid.uuid4(),
        component_id="didact.measurement-lab",
    )

    class Service:
        async def get(self, _activity_id, _org_id):
            return activity

    monkeypatch.setattr(activities, "_service", lambda _db: Service())

    with pytest.raises(Exception, match="component_id does not match"):
        await activities.record_activity_event(
            SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4()),
            StubSession(),
            activity_id,
            body,
        )
