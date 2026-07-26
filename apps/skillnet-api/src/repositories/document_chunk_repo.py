"""Data access for document chunks, including pgvector similarity search.

Shared by document ingestion (Phase 5), chat retrieval (Phase 5), and the
generation pipeline's chunked mode (Phase 4).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Document, DocumentChunk
from src.repositories.base import BaseRepository


class DocumentChunkRepository(BaseRepository[DocumentChunk]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, DocumentChunk)

    async def add_chunk(
        self,
        *,
        document_id: uuid.UUID,
        content: str,
        embedding: list[float],
        chunk_index: int,
        chunk_metadata: dict,
    ) -> DocumentChunk:
        chunk = DocumentChunk(
            document_id=document_id,
            content=content,
            embedding=embedding,
            chunk_index=chunk_index,
            chunk_metadata=chunk_metadata,
        )
        self.session.add(chunk)
        return chunk

    async def delete_for_document(self, document_id: uuid.UUID) -> None:
        chunks = await self.list_for_document_ordered(document_id)
        for chunk in chunks:
            await self.session.delete(chunk)

    async def count_for_document(self, document_id: uuid.UUID) -> int:
        query = select(func.count()).where(DocumentChunk.document_id == document_id)
        return (await self.session.execute(query)).scalar_one()

    async def list_for_document_ordered(
        self, document_id: uuid.UUID
    ) -> Sequence[DocumentChunk]:
        query = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        )
        return (await self.session.execute(query)).scalars().all()

    async def list_for_documents_ordered(
        self, document_ids: Sequence[uuid.UUID]
    ) -> Sequence[DocumentChunk]:
        if not document_ids:
            return []
        query = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id.in_(document_ids))
            .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
        )
        return (await self.session.execute(query)).scalars().all()

    async def similarity_search(
        self,
        *,
        org_id: uuid.UUID,
        query_embedding: list[float],
        top_k: int = 5,
        document_ids: Sequence[uuid.UUID] | None = None,
    ) -> list[dict]:
        """Org-scoped cosine similarity search over chunks."""
        distance = DocumentChunk.embedding.cosine_distance(query_embedding)
        query = (
            select(
                DocumentChunk.id,
                DocumentChunk.document_id,
                DocumentChunk.content,
                DocumentChunk.chunk_metadata,
                Document.title.label("document_title"),
                (1 - distance).label("similarity"),
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.org_id == org_id)
        )
        if document_ids:
            query = query.where(DocumentChunk.document_id.in_(document_ids))
        query = query.order_by(distance).limit(top_k)

        rows = (await self.session.execute(query)).all()
        return [
            {
                "chunk_id": row.id,
                "document_id": row.document_id,
                "content": row.content,
                "metadata": row.chunk_metadata,
                "document_title": row.document_title,
                "similarity": float(row.similarity),
            }
            for row in rows
        ]

    async def similarity_search_by_headings(
        self,
        *,
        org_id: uuid.UUID,
        query_embedding: list[float],
        top_k: int = 8,
        document_ids: Sequence[uuid.UUID] | None = None,
        headings: Sequence[str] | None = None,
    ) -> list[dict]:
        """Same as :meth:`similarity_search`, restricted to a set of section headings.

        Adds ``AND (chunk_metadata->>'heading') = ANY(:headings)`` when ``headings`` is
        non-empty. Used by the v2 runtime's ``load_context`` (§4.2) to scope retrieval
        to ``course_nodes.source_headings``: headings survive re-ingestion, chunk ids do
        not. With ``headings`` empty the behaviour is identical to
        :meth:`similarity_search` with ``top_k=8``, which is also the documented retry
        when the heading filter returns nothing.
        """
        distance = DocumentChunk.embedding.cosine_distance(query_embedding)
        query = (
            select(
                DocumentChunk.id,
                DocumentChunk.document_id,
                DocumentChunk.content,
                DocumentChunk.chunk_metadata,
                Document.title.label("document_title"),
                (1 - distance).label("similarity"),
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.org_id == org_id)
        )
        if document_ids:
            query = query.where(DocumentChunk.document_id.in_(document_ids))
        if headings:
            query = query.where(
                DocumentChunk.chunk_metadata["heading"].astext.in_(list(headings))
            )
        query = query.order_by(distance).limit(top_k)

        rows = (await self.session.execute(query)).all()
        return [
            {
                "chunk_id": row.id,
                "document_id": row.document_id,
                "content": row.content,
                "metadata": row.chunk_metadata,
                "document_title": row.document_title,
                "similarity": float(row.similarity),
            }
            for row in rows
        ]
