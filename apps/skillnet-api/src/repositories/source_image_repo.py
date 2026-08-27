"""Source image data access."""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import SourceImage
from src.repositories.base import BaseRepository


class SourceImageRepository(BaseRepository[SourceImage]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, SourceImage)

    async def get_scoped(
        self, id: uuid.UUID, org_id: uuid.UUID, document_id: uuid.UUID
    ) -> SourceImage | None:
        """One image, only if it belongs to this org *and* this document.

        Both predicates, not just the org: the asset route addresses an image through the
        document that owns it, and a route that accepted any org image under any document
        id would leak which images exist elsewhere in the organization.
        """
        image = await self.get_by_id(id)
        if image is None or image.org_id != org_id or image.document_id != document_id:
            return None
        return image

    async def list_for_document(
        self, document_id: uuid.UUID, *, include_decorative: bool = False
    ) -> Sequence[SourceImage]:
        query = select(SourceImage).where(SourceImage.document_id == document_id)
        if not include_decorative:
            query = query.where(SourceImage.is_decorative.is_(False))
        query = query.order_by(SourceImage.page, SourceImage.extracted_at)
        return (await self.session.execute(query)).scalars().all()

    async def delete_for_document(self, document_id: uuid.UUID) -> None:
        """Drop every row for a document, so re-ingestion replaces rather than duplicates."""
        await self.session.execute(
            delete(SourceImage).where(SourceImage.document_id == document_id)
        )

    async def count_reusable(
        self, document_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        """Non-decorative images per document, for the ids asked about.

        One grouped query for a whole page of documents rather than a count per row, and
        documents with no images are simply absent from the mapping (the caller defaults
        to zero). This is what lets the creation screen offer or grey out "reuse the
        document's own images" *before* a course exists, instead of after.
        """
        if not document_ids:
            return {}
        query = (
            select(SourceImage.document_id, func.count())
            .where(
                SourceImage.document_id.in_(list(document_ids)),
                SourceImage.is_decorative.is_(False),
            )
            .group_by(SourceImage.document_id)
        )
        rows = (await self.session.execute(query)).all()
        return {document_id: count for document_id, count in rows}
