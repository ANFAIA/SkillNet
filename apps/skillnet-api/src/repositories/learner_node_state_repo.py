"""Per-(user, node) state data access, plus the one place a :class:`Transition` is
applied to a row.

Keeping ``apply_transition`` here is what lets ``mastery_service`` stay pure: the rule
decides *what* changes, the repository performs the write and owns the clock.

It also owns the one read that spans the node graph and the learner's state:
``unmastered_prerequisites``, which feeds
``NodeSignalContext.unmastered_prerequisites`` (§3.3, ``revisar_prerrequisito``).
The rule lives in ``learner_profile_service`` and stays pure; the join lives here.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.models import (
    CourseNode,
    CourseNodePrerequisite,
    LearnerNodeState,
    NodeState,
)
from src.repositories.base import BaseRepository
from src.services.mastery_service import Transition


def unmastered_prerequisites_query(
    *, user_id: uuid.UUID, node_id: uuid.UUID
) -> Select:
    """Prerequisites of ``node_id`` this learner has not mastered (§3.3).

    Two details carry the whole correctness of the ``revisar_prerrequisito``
    trigger, and both are easy to get silently wrong:

    * **The join to ``learner_node_states`` must be a LEFT join.** A prerequisite
      the learner has never opened has *no* row at all. With an inner join the
      query would return nothing for exactly the learner the rule exists for — the
      one who failed a conceptual question because they skipped the groundwork —
      and the trigger would never fire.
    * **Archived prerequisites are excluded.** §11.1 archives rather than deletes a
      node somebody worked on, so an archived node keeps its edges. Counting one
      would send a learner back to review a node the course no longer teaches, with
      no way to ever clear it.
    """
    prerequisite = aliased(CourseNode)
    return (
        select(CourseNodePrerequisite.prerequisite_node_id)
        .join(
            prerequisite,
            prerequisite.id == CourseNodePrerequisite.prerequisite_node_id,
        )
        .outerjoin(
            LearnerNodeState,
            and_(
                LearnerNodeState.node_id
                == CourseNodePrerequisite.prerequisite_node_id,
                LearnerNodeState.user_id == user_id,
            ),
        )
        .where(
            CourseNodePrerequisite.node_id == node_id,
            prerequisite.archived.is_(False),
            or_(
                LearnerNodeState.id.is_(None),
                LearnerNodeState.state != NodeState.MASTERED,
            ),
        )
    )


class LearnerNodeStateRepository(BaseRepository[LearnerNodeState]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, LearnerNodeState)

    async def get_by_user_and_node(
        self, user_id: uuid.UUID, node_id: uuid.UUID
    ) -> LearnerNodeState | None:
        query = select(LearnerNodeState).where(
            LearnerNodeState.user_id == user_id,
            LearnerNodeState.node_id == node_id,
        )
        return (await self.session.execute(query)).scalar_one_or_none()

    async def get_or_create(
        self, *, user_id: uuid.UUID, node_id: uuid.UUID, mastery: float = 0.0
    ) -> LearnerNodeState:
        """Fetch the row or seed it. ``mastery`` is the prior from ``user_skills``
        (§7.1) — a starting point for the EWMA and the scaffold band, never a reason
        to skip the node."""
        existing = await self.get_by_user_and_node(user_id, node_id)
        if existing is not None:
            return existing
        return await self.create(user_id=user_id, node_id=node_id, mastery=mastery)

    async def states_for_nodes(
        self, *, user_id: uuid.UUID, node_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, LearnerNodeState]:
        """Used by ``GET /courses/{id}/nodes`` to avoid one query per node."""
        if not node_ids:
            return {}
        query = select(LearnerNodeState).where(
            LearnerNodeState.user_id == user_id,
            LearnerNodeState.node_id.in_(list(node_ids)),
        )
        rows = (await self.session.execute(query)).scalars().all()
        return {row.node_id: row for row in rows}

    async def unmastered_prerequisites(
        self, *, user_id: uuid.UUID, node_id: uuid.UUID
    ) -> list[uuid.UUID]:
        """The ids, not just the count — the tutor names the node to go back to.

        ``len()`` of this is what ``NodeSignalContext.unmastered_prerequisites``
        wants; the ids are what ``revisar_prerrequisito`` needs to be actionable.
        """
        rows = (
            await self.session.execute(
                unmastered_prerequisites_query(user_id=user_id, node_id=node_id)
            )
        ).scalars().all()
        return list(rows)

    async def apply_transition(
        self,
        state: LearnerNodeState,
        transition: Transition,
        *,
        now: datetime | None = None,
    ) -> LearnerNodeState:
        """Write one transition of §7.3 onto the row.

        Timestamps are stamped here (never inside the pure rule), ``first_seen_at``
        only if it is still empty, and ``mastered_at`` only if the row was not already
        mastered — so re-running a transition is idempotent on the timestamps.
        """
        moment = now or datetime.now(timezone.utc)

        state.state = NodeState(transition.to_state)
        for column, value in transition.changes.items():
            setattr(state, column, value)

        if transition.attempts_delta:
            state.attempts_count = (state.attempts_count or 0) + transition.attempts_delta
        if transition.stamp_first_seen_at and state.first_seen_at is None:
            state.first_seen_at = moment
        if transition.stamp_mastered_at and state.mastered_at is None:
            state.mastered_at = moment
        state.updated_at = moment

        await self.session.flush()
        return state

    async def waive(
        self,
        state: LearnerNodeState,
        *,
        waived_by: uuid.UUID,
        now: datetime | None = None,
    ) -> LearnerNodeState:
        """The human escape hatch of §7.4 (``POST /nodes/{id}/waive``).

        Sets ``mastered`` with ``waived_by``/``waived_at``. The ``audit_log`` row
        (``action='node_waived'``) is written by the route, which knows the actor.
        Mastery is left untouched: a waiver is an accreditation by a human who has
        seen the person work, not a measured score, and inventing a number here would
        end up printed on a certificate as if it had been measured.
        """
        moment = now or datetime.now(timezone.utc)
        state.state = NodeState.MASTERED
        state.waived_by = waived_by
        state.waived_at = moment
        if state.mastered_at is None:
            state.mastered_at = moment
        state.updated_at = moment
        await self.session.flush()
        return state
