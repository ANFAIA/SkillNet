"""Data access for document chunks, including pgvector similarity search.

Shared by document ingestion (Phase 5), chat retrieval (Phase 5), and the
generation pipeline's chunked mode (Phase 4).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Document, DocumentChunk
from src.repositories.base import BaseRepository

#: The dimension Postgres enforces on `document_chunks.embedding`. `atttypmod` stores the
#: number as-is for the `vector` type (unlike `varchar`, which adds 4), and it is read from
#: `pg_attribute` because `information_schema.columns` does not expose the dimension of an
#: extension type. Returns -1 when the column is an unconstrained `vector`.
_DIMENSIONS_SQL = text(
    "SELECT atttypmod FROM pg_attribute "
    "WHERE attrelid = 'document_chunks'::regclass AND attname = 'embedding' "
    "AND NOT attisdropped"
)


class DocumentChunkRepository(BaseRepository[DocumentChunk]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, DocumentChunk)

    async def column_dimensions(self) -> int | None:
        """The dimension the database demands, or ``None`` if the column does not constrain it.

        The source of truth for embedding size. ``DocumentChunk.embedding`` no longer
        declares it, precisely so that this is the only place it lives.
        """
        typmod = (await self.session.execute(_DIMENSIONS_SQL)).scalar_one_or_none()
        if typmod is None or typmod < 0:
            return None
        return int(typmod)

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

    async def search_chunks_fts(
        self,
        *,
        org_id: uuid.UUID,
        terms: Sequence[str],
        top_k: int = 5,
        document_ids: Sequence[uuid.UUID] | None = None,
    ) -> list[dict]:
        """Org-scoped Spanish full-text search over chunks.

        The lexical half of retrieval, and the one that actually works today: with
        ``EMBEDDING_MODEL=fixture/local`` every vector is a hashed random unit vector, so
        :meth:`similarity_search` returns five arbitrary passages and they are all dropped
        by ``retrieval.SIMILARITY_FLOOR``. This query needs no embedding provider at all.

        **``terms``, already cleaned, and OR-ed — not the raw question.** Handing the
        question straight to ``websearch_to_tsquery`` is the obvious version and it
        retrieves nothing: that parser joins words with ``&``, so *"cuales son los 14
        alergenos de declaracion obligatoria"* compiles to
        ``'cual' & '14' & 'alergen' & 'declaracion' & 'obligatori'`` and no single chunk
        holds all five. Measured on the seeded corpus: 0 rows for the question, 7 rows for
        ``alergenos`` alone. OR-ing the terms and letting the rank discriminate puts the
        section actually titled *"Los catorce alergenos de declaracion obligatoria"* at
        the top.

        Still ``websearch_to_tsquery`` and not ``to_tsquery``, via its ``or`` keyword: the
        websearch parser never raises on its input, and these terms are interpolated into
        a query string. ``to_tsquery`` would turn a stray ``&`` into a syntax error and an
        unbalanced quote into an exception on a user-typed question.

        ``ts_rank_cd`` rather than ``ts_rank``: cover density rewards matches that sit
        *close together*, which is what distinguishes a passage genuinely about the
        question from one that happens to mention each of its words in a different
        paragraph.

        Returns the same dict shape as :meth:`similarity_search` so ``assemble_context``
        consumes either without knowing which ran, but scores under ``rank`` rather than
        ``similarity`` — the two are not on a comparable scale, and putting a
        ``ts_rank_cd`` value (typically well under 0.5) into ``similarity`` would feed it
        to a cosine threshold of 0.25 and filter away almost every row.
        """
        if not terms:
            return []

        tsquery = func.websearch_to_tsquery("spanish", " or ".join(terms))
        rank = func.ts_rank_cd(DocumentChunk.search_vector, tsquery)
        statement = (
            select(
                DocumentChunk.id,
                DocumentChunk.document_id,
                DocumentChunk.content,
                DocumentChunk.chunk_metadata,
                Document.title.label("document_title"),
                rank.label("rank"),
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                Document.org_id == org_id,
                DocumentChunk.search_vector.op("@@")(tsquery),
            )
        )
        if document_ids:
            statement = statement.where(DocumentChunk.document_id.in_(document_ids))
        statement = statement.order_by(rank.desc()).limit(top_k)

        rows = (await self.session.execute(statement)).all()
        return [
            {
                "chunk_id": row.id,
                "document_id": row.document_id,
                "content": row.content,
                "metadata": row.chunk_metadata,
                "document_title": row.document_title,
                "rank": float(row.rank),
            }
            for row in rows
        ]

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
