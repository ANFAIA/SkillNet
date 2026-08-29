"""Data access for the per-(user, activity) counters of ``learner_activity_states``.

Three writers and nothing else: ``POST /activities/{id}/evaluate`` counts one graded
submission, ``POST /activities/{id}/hint`` spends one unit of the disclosure budget, and
``POST /activities/{id}/solution`` stamps the reveal. Reads are counts; there is no client
input on any of these paths, by design (§11.3: the server owns the hint count).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.activity_definition import ActivityDefinition
from src.models.base import aware_utc_now
from src.models.learner_activity_state import LearnerActivityState
from src.repositories.base import BaseRepository


class LearnerActivityStateRepository(BaseRepository[LearnerActivityState]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, LearnerActivityState)

    async def get_for_learner(
        self, activity_id: uuid.UUID, user_id: uuid.UUID
    ) -> LearnerActivityState | None:
        query = select(LearnerActivityState).where(
            LearnerActivityState.activity_id == activity_id,
            LearnerActivityState.user_id == user_id,
        )
        return (await self.session.execute(query)).scalar_one_or_none()

    async def get_or_create(
        self, *, activity: ActivityDefinition, user_id: uuid.UUID
    ) -> LearnerActivityState:
        """Fetch the counters of one learner on one activity, or seed them at zero.

        ``org_id`` is copied from the activity rather than from the caller's session so a
        row can never be filed under a tenant that does not own the definition it counts.
        """
        existing = await self.get_for_learner(activity.id, user_id)
        if existing is not None:
            return existing
        return await self.create(
            org_id=activity.org_id, activity_id=activity.id, user_id=user_id
        )

    async def record_attempt(
        self, *, activity: ActivityDefinition, user_id: uuid.UUID, passed: bool
    ) -> LearnerActivityState:
        """Count one graded submission of this activity, and whether it missed.

        Called **after** the verdict has been applied, because ``item_failures`` is
        contracted as the failures standing *before* this answer: incrementing first would
        make rule 8 fire one failure early.
        """
        row = await self.get_or_create(activity=activity, user_id=user_id)
        row.attempts_count = int(row.attempts_count or 0) + 1
        if not passed:
            row.failures_count = int(row.failures_count or 0) + 1
        await self.session.flush()
        return row

    async def record_hint(
        self, *, activity: ActivityDefinition, user_id: uuid.UUID, level: int
    ) -> LearnerActivityState:
        """Record that ``level`` hints have now been disclosed for this activity.

        ``max`` rather than ``+= 1`` for the same reason the node ladder writes the level
        it just served: the number is a high-water mark of what the learner has been told,
        so two racing requests can only ever agree on the larger one.
        """
        row = await self.get_or_create(activity=activity, user_id=user_id)
        row.hints_used = max(int(row.hints_used or 0), int(level))
        await self.session.flush()
        return row

    async def mark_solution_revealed(
        self,
        *,
        activity: ActivityDefinition,
        user_id: uuid.UUID,
        now: datetime | None = None,
    ) -> LearnerActivityState:
        """Stamp the reveal, once. Idempotent, and it never touches mastery.

        The twin of ``LearnerNodeStateRepository.mark_completed``: a fact about what the
        learner was shown, kept in its own column so nothing reads it as a demonstration.
        """
        row = await self.get_or_create(activity=activity, user_id=user_id)
        if row.solution_revealed_at is None:
            row.solution_revealed_at = now or aware_utc_now()
            await self.session.flush()
        return row


__all__ = ["LearnerActivityStateRepository"]
