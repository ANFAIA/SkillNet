"""Data access for ``media_artifacts`` — the rich-media spine's rows.

Org-scoped like ``node_renders``: a course-level artifact is shared by the whole
organization, so every read a route makes goes through :meth:`get_scoped`, which proves the
row belongs to the caller's org before anything is served.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import MediaArtifact
from src.repositories.base import BaseRepository


class MediaArtifactRepository(BaseRepository[MediaArtifact]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, MediaArtifact)

    async def get_scoped(
        self, artifact_id: uuid.UUID, org_id: uuid.UUID
    ) -> MediaArtifact | None:
        """One artifact of the caller's organization, or ``None``."""
        query = select(MediaArtifact).where(
            MediaArtifact.id == artifact_id, MediaArtifact.org_id == org_id
        )
        return (await self.session.execute(query)).scalar_one_or_none()

    async def list_for_course(
        self,
        course_id: uuid.UUID,
        org_id: uuid.UUID,
        node_id: uuid.UUID | None = None,
    ) -> Sequence[MediaArtifact]:
        """Every artifact of a course, newest first.

        With ``node_id`` set, narrows to the artifacts of that node; left ``None`` the whole
        course is returned (both node-scoped and course-level artifacts). Org-scoped like
        every read here, so the caller only ever sees its own organization's rows.
        """
        query = select(MediaArtifact).where(
            MediaArtifact.course_id == course_id,
            MediaArtifact.org_id == org_id,
        )
        if node_id is not None:
            query = query.where(MediaArtifact.node_id == node_id)
        query = query.order_by(MediaArtifact.created_at.desc())
        return (await self.session.execute(query)).scalars().all()
