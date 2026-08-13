"""Pure, read-only projection of Didact EventPort evidence.

The projection intentionally records observations, not pedagogical conclusions:
``started`` is exposure and ``completed`` is completion of an activity interaction.
Neither implies success or mastery. Learner responses never enter this module.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

DidactEvidenceKind = Literal[
    "exposure",
    "attempt",
    "response",
    "feedback",
    "completion",
]

DIDACT_EVIDENCE_TYPE_TO_KIND: dict[str, DidactEvidenceKind] = {
    "didact.started": "exposure",
    "didact.attempted": "attempt",
    "didact.answered": "response",
    "didact.feedback_viewed": "feedback",
    "didact.completed": "completion",
}


@dataclass(frozen=True)
class DidactEvidenceEvent:
    """Minimal event projection; it deliberately excludes the telemetry payload."""

    event_id: uuid.UUID
    type: str
    occurred_at: datetime


@dataclass(frozen=True)
class EvidenceStage:
    count: int = 0
    first_occurred_at: datetime | None = None
    last_occurred_at: datetime | None = None

    @property
    def observed(self) -> bool:
        return self.count > 0


@dataclass(frozen=True)
class DidactEvidenceSummary:
    exposure: EvidenceStage
    attempt: EvidenceStage
    response: EvidenceStage
    feedback: EvidenceStage
    completion: EvidenceStage


class DidactEvidenceSource(Protocol):
    async def didact_evidence_for_node(
        self, *, user_id: uuid.UUID, node_id: uuid.UUID
    ) -> list[DidactEvidenceEvent]: ...


class DidactEvidenceReader:
    """Read-only orchestration around the pure projection."""

    def __init__(self, source: DidactEvidenceSource) -> None:
        self.source = source

    async def for_learner_node(
        self, *, user_id: uuid.UUID, node_id: uuid.UUID
    ) -> DidactEvidenceSummary:
        events = await self.source.didact_evidence_for_node(
            user_id=user_id,
            node_id=node_id,
        )
        return summarize_didact_evidence(events)


def summarize_didact_evidence(
    events: Sequence[DidactEvidenceEvent],
) -> DidactEvidenceSummary:
    """Summarize a replay safely, independent of delivery order.

    Event ids are the idempotency key. Sorting by occurrence time makes first/last
    stable when callers replay the same events in a different delivery order.
    Unknown event types (including any future mastery signal) are ignored until an
    explicit evidence mapping is added above.
    """

    ordered: list[DidactEvidenceEvent] = []
    seen_ids: set[uuid.UUID] = set()
    for event in sorted(
        events,
        key=lambda item: (item.occurred_at, item.event_id.hex, item.type),
    ):
        if event.event_id not in seen_ids:
            seen_ids.add(event.event_id)
            ordered.append(event)
    observations: dict[DidactEvidenceKind, list[datetime]] = {
        "exposure": [],
        "attempt": [],
        "response": [],
        "feedback": [],
        "completion": [],
    }
    for event in ordered:
        kind = DIDACT_EVIDENCE_TYPE_TO_KIND.get(event.type)
        if kind is not None:
            observations[kind].append(event.occurred_at)

    def stage(kind: DidactEvidenceKind) -> EvidenceStage:
        timestamps = observations[kind]
        return EvidenceStage(
            count=len(timestamps),
            first_occurred_at=timestamps[0] if timestamps else None,
            last_occurred_at=timestamps[-1] if timestamps else None,
        )

    return DidactEvidenceSummary(
        exposure=stage("exposure"),
        attempt=stage("attempt"),
        response=stage("response"),
        feedback=stage("feedback"),
        completion=stage("completion"),
    )
