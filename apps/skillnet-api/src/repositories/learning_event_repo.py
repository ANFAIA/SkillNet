"""Append-only access to ``learning_events``.

Two shapes travel across this boundary and both are plain dataclasses so the pure
half of ``learner_profile_service`` (and its tests) never needs a session:

* :class:`EventInput` — what the caller wants to append.
* :class:`EventSample` — the three columns the 30-day vector window needs.

**Privacy (§3.3):** ordinary node instrumentation only carries ``element_id`` and
``ms``. Didact events use a separate closed schema before this repository receives
their version, activity/component coordinates, timestamp, and bounded telemetry.
No user text, copied content, answers, or solutions cross this boundary.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.learning_event import LearningEvent
from src.personalization.projection import ValidatedHistoryEvent
from src.repositories.base import BaseRepository
from src.services.didact_evidence import (
    DIDACT_EVIDENCE_TYPE_TO_KIND,
    DidactEvidenceEvent,
)


@dataclass(frozen=True)
class EventInput:
    """One event to append. ``weight`` is set by the service from ``EVENT_WEIGHTS``."""

    type: str
    element: str | None = None
    node_id: uuid.UUID | None = None
    weight: float = 0.0
    element_id: str | None = None
    ms: int | None = None


@dataclass(frozen=True)
class EventSample:
    """A row of the vector window: dimension, effective weight, timestamp."""

    element: str | None
    weight: float
    created_at: datetime


class LearningEventRepository(BaseRepository[LearningEvent]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, LearningEvent)

    async def record_many(
        self, *, user_id: uuid.UUID, events: Sequence[EventInput]
    ) -> list[LearningEvent]:
        """Insert a batch. Returns the ORM rows (flushed, not committed)."""
        if not events:
            return []
        rows = [
            LearningEvent(
                user_id=user_id,
                node_id=event.node_id,
                type=event.type,
                element=event.element,
                weight=event.weight,
                event_metadata=_metadata(event),
            )
            for event in events
        ]
        self.session.add_all(rows)
        await self.session.flush()
        return rows

    async def record_didact_event(
        self,
        *,
        event_id: uuid.UUID,
        user_id: uuid.UUID,
        node_id: uuid.UUID,
        event_type: str,
        metadata: dict[str, Any],
    ) -> bool:
        """Insert one zero-weight Didact event, ignoring a repeated ``event_id``."""
        statement = (
            insert(LearningEvent)
            .values(
                id=event_id,
                user_id=user_id,
                node_id=node_id,
                type=f"didact.{event_type}",
                element=None,
                weight=0.0,
                event_metadata=metadata,
            )
            .on_conflict_do_nothing(index_elements=[LearningEvent.id])
        )
        result = await self.session.execute(statement)
        return bool(result.rowcount)

    async def window_samples(
        self, *, user_id: uuid.UUID, since: datetime
    ) -> list[EventSample]:
        """Rows inside the vector window, newest first.

        The decay and the L1 normalization are done in Python
        (``compute_format_vector``) on purpose: that keeps the arithmetic of §3.3
        unit-testable without Postgres, and the window is bounded by design
        (90-day retention, one user).
        """
        query = (
            select(
                LearningEvent.element,
                LearningEvent.weight,
                LearningEvent.created_at,
            )
            .where(
                LearningEvent.user_id == user_id,
                LearningEvent.created_at >= since,
                # EventPort evidence is measurement-only until a product decision
                # explicitly maps an event to a format dimension and weight.
                ~LearningEvent.type.startswith("didact."),
            )
            .order_by(LearningEvent.created_at.desc())
        )
        result = await self.session.execute(query)
        return [
            EventSample(element=element, weight=float(weight), created_at=created_at)
            for element, weight, created_at in result.all()
        ]

    async def didact_evidence_for_node(
        self, *, user_id: uuid.UUID, node_id: uuid.UUID
    ) -> list[DidactEvidenceEvent]:
        """Read the minimal evidence stream for exactly one learner and node."""

        query = (
            select(
                LearningEvent.id,
                LearningEvent.type,
                LearningEvent.event_metadata,
                LearningEvent.created_at,
            )
            .where(
                LearningEvent.user_id == user_id,
                LearningEvent.node_id == node_id,
                LearningEvent.type.in_(DIDACT_EVIDENCE_TYPE_TO_KIND),
            )
            .order_by(LearningEvent.created_at.asc(), LearningEvent.id.asc())
        )
        result = await self.session.execute(query)
        evidence: list[DidactEvidenceEvent] = []
        for event_id, event_type, metadata, created_at in result.all():
            occurred_at = _occurred_at(metadata, fallback=created_at)
            evidence.append(
                DidactEvidenceEvent(
                    event_id=event_id,
                    type=event_type,
                    occurred_at=occurred_at,
                )
            )
        return evidence

    async def recent_longitudinal_didact_events(
        self,
        *,
        user_id: uuid.UUID,
        exclude_node_id: uuid.UUID,
        limit: int = 128,
    ) -> list[ValidatedHistoryEvent]:
        """Bounded assessed Didact history from prior nodes.

        Only the closed EventPort fields needed by the pure projector leave the
        repository. Exposure/completion rows are not selected, so they cannot displace
        evaluated evidence or accidentally become a personalization signal.
        """

        query = (
            select(
                LearningEvent.id,
                LearningEvent.type,
                LearningEvent.event_metadata,
            )
            .where(
                LearningEvent.user_id == user_id,
                LearningEvent.node_id != exclude_node_id,
                LearningEvent.type.in_(
                    ("didact.answered", "didact.feedback_viewed")
                ),
            )
            .order_by(LearningEvent.created_at.desc(), LearningEvent.id.desc())
            .limit(max(1, min(int(limit), 256)))
        )
        result = await self.session.execute(query)
        projected: list[ValidatedHistoryEvent] = []
        for event_id, event_type, raw_metadata in result.all():
            metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
            if metadata.get("schema_version") != 1:
                continue
            component_id = metadata.get("component_id")
            payload = metadata.get("payload")
            if not isinstance(component_id, str) or not component_id.startswith("didact."):
                continue
            if not isinstance(payload, dict):
                payload = {}
            attempt_id = payload.get("attempt_id")
            outcome = payload.get("outcome")
            raw_score = payload.get("score")
            try:
                score = float(raw_score) if raw_score is not None else None
            except (TypeError, ValueError):
                score = None
            projected.append(
                ValidatedHistoryEvent(
                    event_id=str(event_id),
                    type=str(event_type),
                    component_id=component_id,
                    attempt_id=str(attempt_id) if attempt_id else None,
                    outcome=str(outcome) if outcome else None,
                    score=score,
                )
            )
        return projected

    async def recent_types_for_node(
        self, *, user_id: uuid.UUID, node_id: uuid.UUID, limit: int = 3
    ) -> list[str]:
        """Most recent event types on one node, **newest first**.

        This is what feeds ``NodeSignalContext.recent_event_types``, i.e. the
        ``reducir_longitud_modulo`` rule.
        """
        query = (
            select(LearningEvent.type)
            .where(
                LearningEvent.user_id == user_id,
                LearningEvent.node_id == node_id,
                # Didact EventPort is measurement-only in its first cut. Even zero-weight
                # rows must not displace the three legacy signals used for adaptation.
                ~LearningEvent.type.startswith("didact."),
            )
            .order_by(LearningEvent.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def delete_for_user(self, user_id: uuid.UUID) -> int:
        """Erase every event of one user (art. 17; also used by the purge script)."""
        result = await self.session.execute(
            delete(LearningEvent).where(LearningEvent.user_id == user_id)
        )
        return result.rowcount or 0


def _metadata(event: EventInput) -> dict[str, Any]:
    """The only two keys ``learning_events.metadata`` may ever contain."""
    payload: dict[str, Any] = {}
    if event.element_id is not None:
        payload["element_id"] = event.element_id
    if event.ms is not None:
        payload["ms"] = int(event.ms)
    return payload


def _occurred_at(metadata: dict[str, Any], *, fallback: datetime) -> datetime:
    value = metadata.get("occurred_at")
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return fallback
