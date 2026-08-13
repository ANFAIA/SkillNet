import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.repositories.learning_event_repo import LearningEventRepository
from src.services.didact_evidence import (
    DidactEvidenceEvent,
    DidactEvidenceReader,
    summarize_didact_evidence,
)

NOW = datetime(2026, 8, 13, 5, 0, tzinfo=timezone.utc)


def event(event_type: str, *, seconds: int, event_id: uuid.UUID | None = None):
    return DidactEvidenceEvent(
        event_id=event_id or uuid.uuid4(),
        type=f"didact.{event_type}",
        occurred_at=NOW + timedelta(seconds=seconds),
    )


def test_summary_distinguishes_each_observed_evidence_stage():
    summary = summarize_didact_evidence(
        [
            event("started", seconds=0),
            event("attempted", seconds=1),
            event("answered", seconds=2),
            event("feedback_viewed", seconds=3),
            event("completed", seconds=4),
        ]
    )

    assert summary.exposure.observed
    assert summary.attempt.observed
    assert summary.response.observed
    assert summary.feedback.observed
    assert summary.completion.observed
    assert summary.completion.count == 1


def test_summary_is_stable_for_out_of_order_replay():
    replayed_id = uuid.uuid4()
    first = event("attempted", seconds=5, event_id=replayed_id)
    replay = event("attempted", seconds=5, event_id=replayed_id)
    earlier = event("attempted", seconds=1)

    summary = summarize_didact_evidence([first, replay, earlier])

    assert summary.attempt.count == 2
    assert summary.attempt.first_occurred_at == earlier.occurred_at
    assert summary.attempt.last_occurred_at == first.occurred_at
    assert summarize_didact_evidence([earlier, replay, first]) == summary


def test_started_and_unknown_mastery_do_not_infer_completion_or_success():
    summary = summarize_didact_evidence(
        [event("started", seconds=0), event("mastered", seconds=1)]
    )

    assert summary.exposure.count == 1
    assert not summary.attempt.observed
    assert not summary.response.observed
    assert not summary.completion.observed


@pytest.mark.asyncio
async def test_reader_keeps_learner_and_node_scope_intact():
    user_id = uuid.uuid4()
    node_id = uuid.uuid4()

    class Source:
        async def didact_evidence_for_node(self, **scope):
            self.scope = scope
            return [event("completed", seconds=1)]

    source = Source()
    summary = await DidactEvidenceReader(source).for_learner_node(
        user_id=user_id,
        node_id=node_id,
    )

    assert source.scope == {"user_id": user_id, "node_id": node_id}
    assert summary.completion.count == 1


@pytest.mark.asyncio
async def test_repository_read_is_isolated_to_learner_and_node_and_ordered():
    class Result:
        def all(self):
            return []

    class Session:
        async def execute(self, statement):
            self.statement = statement
            return Result()

    user_id = uuid.uuid4()
    node_id = uuid.uuid4()
    session = Session()

    rows = await LearningEventRepository(session).didact_evidence_for_node(
        user_id=user_id,
        node_id=node_id,
    )

    assert rows == []
    compiled = session.statement.compile()
    assert user_id in compiled.params.values()
    assert node_id in compiled.params.values()
    assert "learning_events.user_id" in str(compiled)
    assert "learning_events.node_id" in str(compiled)
    assert "ORDER BY learning_events.created_at ASC, learning_events.id ASC" in str(compiled)
