"""Document data access."""

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.models import Document, DocumentStatus
from src.repositories.base import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Document)

    async def get_scoped(self, id: uuid.UUID, org_id: uuid.UUID) -> Document | None:
        doc = await self.get_by_id(id)
        if doc is None or doc.org_id != org_id:
            return None
        return doc

    async def list_documents(
        self,
        *,
        org_id: uuid.UUID,
        status: DocumentStatus | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[Document], int]:
        filters: list[ColumnElement[bool]] = [Document.org_id == org_id]
        if status is not None:
            filters.append(Document.status == status)
        return await self.list(
            filters=filters,
            order_by=Document.created_at.desc(),
            offset=offset,
            limit=limit,
        )
