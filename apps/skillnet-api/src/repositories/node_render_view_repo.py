"""Read auditing for shared renders (``node_render_views``, §2.1).

``node_renders`` is content and has no ``user_id``: on a cache hit — the ~80 % that makes
the cost model work — the row has nothing to do with the employee reading it. So "who saw
what, and when" lives here, one thin row written on the **first** ``GET /nodes/{id}/render``
of each user.

A certificate is justified by joining ``node_attempts`` -> ``node_render_views`` ->
``node_renders``, and it survives the deletion of any other user because
``node_renders.generated_by`` is ``ON DELETE SET NULL``.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import NodeRenderView


class NodeRenderViewRepository:
    """Not a ``BaseRepository``: the table has a composite primary key and no ``id``."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(
        self, *, user_id: uuid.UUID, render_id: uuid.UUID
    ) -> NodeRenderView | None:
        query = select(NodeRenderView).where(
            NodeRenderView.user_id == user_id,
            NodeRenderView.render_id == render_id,
        )
        return (await self.session.execute(query)).scalar_one_or_none()

    async def record_first_view(
        self, *, user_id: uuid.UUID, render_id: uuid.UUID, node_id: uuid.UUID
    ) -> NodeRenderView:
        """Idempotent: ``first_seen_at`` means *first*, so a re-read never moves it.

        The primary key ``(user_id, render_id)`` is the real guard; the pre-check only
        avoids a pointless round trip in the common case.
        """
        existing = await self.get(user_id=user_id, render_id=render_id)
        if existing is not None:
            return existing
        row = NodeRenderView(user_id=user_id, render_id=render_id, node_id=node_id)
        self.session.add(row)
        try:
            await self.session.flush()
        except IntegrityError:
            # Two tabs opened the node at once. The row exists; that is the whole point.
            await self.session.rollback()
            found = await self.get(user_id=user_id, render_id=render_id)
            if found is None:  # pragma: no cover - the primary key says otherwise
                raise
            return found
        return row

    async def render_ids_for_node(
        self, *, user_id: uuid.UUID, node_id: uuid.UUID, limit: int = 20
    ) -> list[uuid.UUID]:
        """Renders this learner has been served on this node, newest first (§5.5)."""
        query = (
            select(NodeRenderView.render_id)
            .where(
                NodeRenderView.user_id == user_id,
                NodeRenderView.node_id == node_id,
            )
            .order_by(NodeRenderView.first_seen_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(query)).scalars().all())

    async def list_for_node(
        self, *, user_id: uuid.UUID, node_id: uuid.UUID, limit: int = 20
    ) -> Sequence[NodeRenderView]:
        query = (
            select(NodeRenderView)
            .where(
                NodeRenderView.user_id == user_id,
                NodeRenderView.node_id == node_id,
            )
            .order_by(NodeRenderView.first_seen_at.desc())
            .limit(limit)
        )
        return (await self.session.execute(query)).scalars().all()


__all__ = ["NodeRenderViewRepository"]
