"""Per-item attempt data access for v2 nodes.

Separate table from ``exercise_attempts`` because that one requires
``exercise_id NOT NULL REFERENCES exercises(id)`` and items generated at runtime are
not rows of ``exercises`` (§3.4).
"""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import NodeAttempt
from src.repositories.base import BaseRepository


class NodeAttemptRepository(BaseRepository[NodeAttempt]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, NodeAttempt)

    async def record(self, **kwargs: Any) -> NodeAttempt:
        """Append one graded attempt. Alias of ``create`` with a name that says the
        table is append-only."""
        return await self.create(**kwargs)

    async def count_for_item(
        self, *, user_id: uuid.UUID, node_id: uuid.UUID, item_id: str
    ) -> int:
        """Attempts already recorded for this item — the ``attempt-before-hint`` gate
        of §7.4 (a hint is refused while this is 0)."""
        query = select(func.count()).where(
            NodeAttempt.user_id == user_id,
            NodeAttempt.node_id == node_id,
            NodeAttempt.item_id == item_id,
        )
        return int((await self.session.execute(query)).scalar_one())

    async def count_failures_for_item(
        self, *, user_id: uuid.UUID, node_id: uuid.UUID, item_id: str
    ) -> int:
        """Failures already recorded for this item — feeds ``item_failures``, which is
        what makes transition 8 fire on the 4th failure (§7.4)."""
        query = select(func.count()).where(
            NodeAttempt.user_id == user_id,
            NodeAttempt.node_id == node_id,
            NodeAttempt.item_id == item_id,
            NodeAttempt.passed.is_(False),
        )
        return int((await self.session.execute(query)).scalar_one())

    async def list_for_node(
        self, *, user_id: uuid.UUID, node_id: uuid.UUID, limit: int = 50
    ) -> Sequence[NodeAttempt]:
        query = (
            select(NodeAttempt)
            .where(NodeAttempt.user_id == user_id, NodeAttempt.node_id == node_id)
            .order_by(NodeAttempt.attempted_at.desc())
            .limit(limit)
        )
        return (await self.session.execute(query)).scalars().all()
