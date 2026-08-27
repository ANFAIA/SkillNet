"""Data access for the course node graph (v2 design-time).

Owns three things beyond plain CRUD:

* ``defer_position_constraint`` — ``uq_course_nodes_position`` is
  ``DEFERRABLE INITIALLY IMMEDIATE`` and the schema ``PUT`` must defer it inside
  its transaction, otherwise swapping positions 1 and 2 violates the constraint
  mid-statement (§3.2).
* the prerequisite edge table, which has no ORM relationship by design.
* two read-only aggregates over ``learner_node_states`` that the schema service
  needs and nothing else does: the per-node attempt count that makes a node
  undeletable (§11.1 rule 3) and the mastery rows that recompute enrollment
  closure (§7.5). Writing ``learner_node_states`` stays out of here.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import CourseNode, CourseNodePrerequisite, LearnerNodeState
from src.repositories.base import BaseRepository

POSITION_CONSTRAINT = "uq_course_nodes_position"


class CourseNodeRepository(BaseRepository[CourseNode]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, CourseNode)

    # ----------------------------------------------------------------- nodes --
    async def defer_position_constraint(self) -> None:
        """Defer ``uq_course_nodes_position`` until COMMIT for this transaction."""
        await self.session.execute(text(f"SET CONSTRAINTS {POSITION_CONSTRAINT} DEFERRED"))

    async def get_scoped(
        self, node_id: uuid.UUID, org_id: uuid.UUID
    ) -> CourseNode | None:
        node = await self.get_by_id(node_id)
        if node is None or node.org_id != org_id:
            return None
        return node

    async def list_for_course(
        self, course_id: uuid.UUID, *, include_archived: bool = True
    ) -> Sequence[CourseNode]:
        query = select(CourseNode).where(CourseNode.course_id == course_id)
        if not include_archived:
            query = query.where(CourseNode.archived.is_(False))
        query = query.order_by(CourseNode.position, CourseNode.created_at)
        return (await self.session.execute(query)).scalars().all()

    # --------------------------------------------------------- prerequisites --
    async def prerequisites_for(
        self, node_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[uuid.UUID]]:
        """Return ``{node_id: [prerequisite_node_id, ...]}`` for the given nodes."""
        if not node_ids:
            return {}
        query = select(
            CourseNodePrerequisite.node_id,
            CourseNodePrerequisite.prerequisite_node_id,
        ).where(CourseNodePrerequisite.node_id.in_(node_ids))
        edges: dict[uuid.UUID, list[uuid.UUID]] = {nid: [] for nid in node_ids}
        for node_id, prereq_id in (await self.session.execute(query)).all():
            edges.setdefault(node_id, []).append(prereq_id)
        return edges

    async def replace_prerequisites(
        self, node_id: uuid.UUID, prerequisite_ids: Sequence[uuid.UUID]
    ) -> None:
        """Full replacement: the schema PUT validates the graph as a whole."""
        existing = (
            (
                await self.session.execute(
                    select(CourseNodePrerequisite).where(
                        CourseNodePrerequisite.node_id == node_id
                    )
                )
            )
            .scalars()
            .all()
        )
        for edge in existing:
            await self.session.delete(edge)
        await self.session.flush()

        seen: set[uuid.UUID] = set()
        for prereq_id in prerequisite_ids:
            if prereq_id == node_id or prereq_id in seen:
                continue
            seen.add(prereq_id)
            self.session.add(
                CourseNodePrerequisite(
                    node_id=node_id, prerequisite_node_id=prereq_id
                )
            )
        await self.session.flush()

    # ---------------------------------------------- learner-state aggregates --
    async def attempt_counts(
        self, node_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        """Total attempts recorded per node. Non-zero means the node is undeletable."""
        if not node_ids:
            return {}
        query = (
            select(
                LearnerNodeState.node_id,
                func.coalesce(func.sum(LearnerNodeState.attempts_count), 0),
            )
            .where(LearnerNodeState.node_id.in_(node_ids))
            .group_by(LearnerNodeState.node_id)
        )
        rows = (await self.session.execute(query)).all()
        return {node_id: int(total or 0) for node_id, total in rows}

    async def mastery_rows(
        self, node_ids: Sequence[uuid.UUID]
    ) -> list[tuple[uuid.UUID, uuid.UUID, str, float, datetime | None]]:
        """``(user_id, node_id, state, mastery, completed_at)`` for closure recompute.

        ``completed_at`` is here because ``mastery_service.node_is_done`` reads it: a node
        finished but not mastered counts as done, so omitting it from this projection
        would make ``recompute_enrollment_closure`` **reopen** every enrollment that had
        closed that way, on the next schema edit.
        """
        if not node_ids:
            return []
        query = select(
            LearnerNodeState.user_id,
            LearnerNodeState.node_id,
            LearnerNodeState.state,
            LearnerNodeState.mastery,
            LearnerNodeState.completed_at,
        ).where(LearnerNodeState.node_id.in_(node_ids))
        rows = (await self.session.execute(query)).all()
        return [
            (
                row[0],
                row[1],
                row[2].value if hasattr(row[2], "value") else str(row[2]),
                float(row[3] or 0.0),
                row[4],
            )
            for row in rows
        ]
