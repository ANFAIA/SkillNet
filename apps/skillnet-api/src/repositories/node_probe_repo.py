"""Pre-assessment attempt data access.

The whole anti-retry rule of §3.4 lives in two places: the partial unique index
``uq_node_probes_user_node_version ... WHERE scored`` (migration 0005) and
:meth:`NodeProbeRepository.get_scored`, which is what makes a re-entry serve the
stored verdict instead of dealing a fresh hand.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import NodeProbe
from src.repositories.base import BaseRepository


class NodeProbeRepository(BaseRepository[NodeProbe]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, NodeProbe)

    async def get_scored(
        self, *, user_id: uuid.UUID, node_id: uuid.UUID, schema_version: int
    ) -> NodeProbe | None:
        """The single scored probe for this ``(user, node, schema_version)``, if any.

        Mirrors the partial unique index exactly, so it can return at most one row.
        """
        query = select(NodeProbe).where(
            NodeProbe.user_id == user_id,
            NodeProbe.node_id == node_id,
            NodeProbe.schema_version == schema_version,
            NodeProbe.scored.is_(True),
        )
        return (await self.session.execute(query)).scalar_one_or_none()

    async def latest(
        self, *, user_id: uuid.UUID, node_id: uuid.UUID
    ) -> NodeProbe | None:
        """Most recent probe row of any kind (scored, superseded or diagnostic)."""
        query = (
            select(NodeProbe)
            .where(NodeProbe.user_id == user_id, NodeProbe.node_id == node_id)
            .order_by(NodeProbe.created_at.desc())
            .limit(1)
        )
        return (await self.session.execute(query)).scalars().first()

    async def list_for_node(
        self, *, user_id: uuid.UUID, node_id: uuid.UUID
    ) -> Sequence[NodeProbe]:
        query = (
            select(NodeProbe)
            .where(NodeProbe.user_id == user_id, NodeProbe.node_id == node_id)
            .order_by(NodeProbe.created_at.desc())
        )
        return (await self.session.execute(query)).scalars().all()

    async def next_attempt_no(
        self, *, user_id: uuid.UUID, node_id: uuid.UUID
    ) -> int:
        query = select(func.coalesce(func.max(NodeProbe.attempt_no), 0)).where(
            NodeProbe.user_id == user_id, NodeProbe.node_id == node_id
        )
        return int((await self.session.execute(query)).scalar_one()) + 1

    async def supersede(self, probe: NodeProbe) -> NodeProbe:
        """Flip ``scored`` off so a re-probe can be inserted (§3.4).

        The previous row is kept: it is the evidence of the first attempt, and the
        partial index only constrains rows with ``scored = true``.
        """
        probe.scored = False
        await self.session.flush()
        return probe
