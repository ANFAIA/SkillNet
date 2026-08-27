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

    async def list_course_level(
        self, course_id: uuid.UUID, org_id: uuid.UUID
    ) -> Sequence[MediaArtifact]:
        """Authored course overviews only; excludes node-runtime representations."""
        query = (
            select(MediaArtifact)
            .where(
                MediaArtifact.course_id == course_id,
                MediaArtifact.org_id == org_id,
                MediaArtifact.node_id.is_(None),
            )
            .order_by(MediaArtifact.created_at.desc())
        )
        return (await self.session.execute(query)).scalars().all()

    async def list_asset_paths_for_course(self, course_id: uuid.UUID) -> list[str]:
        """Every on-disk asset path this course's artifacts point at.

        Not org-scoped: the caller is deleting the course row itself and has already
        proved it owns it. Used to know which files to remove once the rows have
        cascaded away.
        """
        query = select(MediaArtifact.asset_path).where(
            MediaArtifact.course_id == course_id,
            MediaArtifact.asset_path.is_not(None),
        )
        return sorted({path for path in (await self.session.execute(query)).scalars()})

    async def paths_still_referenced(self, paths: Sequence[str]) -> set[str]:
        """Which of ``paths`` some artifact still points at.

        The store is content-addressed (``services/media/assets.py``), so two artifacts
        with identical bytes share one file. Deleting a course must not remove a file
        another course's artifact is still serving.
        """
        if not paths:
            return set()
        query = select(MediaArtifact.asset_path).where(
            MediaArtifact.asset_path.in_(list(paths))
        )
        return {path for path in (await self.session.execute(query)).scalars() if path}
