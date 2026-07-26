"""Append-only access to ``learning_events``.

Two shapes travel across this boundary and both are plain dataclasses so the pure
half of ``learner_profile_service`` (and its tests) never needs a session:

* :class:`EventInput` — what the caller wants to append.
* :class:`EventSample` — the three columns the 30-day vector window needs.

**Privacy (§3.3):** ``metadata`` only ever carries ``element_id`` and ``ms``. No
user text, no copied content, nothing else. That invariant is enforced here, in
one place, rather than trusted to every caller.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.learning_event import LearningEvent
from src.repositories.base import BaseRepository


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
            )
            .order_by(LearningEvent.created_at.desc())
        )
        result = await self.session.execute(query)
        return [
            EventSample(element=element, weight=float(weight), created_at=created_at)
            for element, weight, created_at in result.all()
        ]

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
