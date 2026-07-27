"""Document ingestion orchestrator (background task).

Invoked lazily by the ``POST /documents/{id}/process`` seam. Opens its own DB
session, parses the stored file, and either stores the full text (small docs)
or chunks + embeds + persists chunks (large docs). Never raises out: any failure
marks the document ``error`` so the background task exits cleanly.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from src.core.logging import get_logger
from src.deps.db import async_session_factory
from src.llm.embedding import resolve_embedding_config
from src.llm.fixtures import maybe_fixture_embedder
from src.models import Document, DocumentStatus, Organization
from src.repositories.document_chunk_repo import DocumentChunkRepository
from src.services.chunker import chunk_sections
from src.services.document_parser import parse_document

logger = get_logger(__name__)

_ERROR_MESSAGE_MAX = 500


async def ingest_document(document_id: uuid.UUID | str) -> None:
    doc_id = document_id if isinstance(document_id, uuid.UUID) else uuid.UUID(str(document_id))

    async with async_session_factory() as session:
        doc = await session.get(Document, doc_id)
        if doc is None:
            logger.warning("Ingestion skipped: document %s not found", doc_id)
            return

        try:
            doc.status = DocumentStatus.PROCESSING
            await session.commit()

            sections, full_text, page_count = parse_document(
                Path(doc.storage_path), doc.file_type
            )
            doc.page_count = page_count
            doc.full_text = full_text

            chunks = chunk_sections(sections, doc.title)

            if chunks:
                try:
                    org = await session.get(Organization, doc.org_id)
                    org_settings = dict(org.settings) if org and org.settings else {}
                    config = resolve_embedding_config(org_settings)
                    embedder = maybe_fixture_embedder(config)

                    vectors = await embedder.embed_texts(
                        [c.content for c in chunks], prefix="passage: "
                    )

                    repo = DocumentChunkRepository(session)
                    await repo.delete_for_document(doc_id)
                    for chunk, vector in zip(chunks, vectors, strict=True):
                        await repo.add_chunk(
                            document_id=doc_id,
                            content=chunk.content,
                            embedding=vector,
                            chunk_index=chunk.chunk_index,
                            chunk_metadata=chunk.metadata,
                        )

                    doc.embedding_model = config.model
                    doc.embedding_dim = config.dimensions
                    logger.info(
                        "Ingested document %s: %d chunks embedded",
                        doc_id, len(chunks),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Embedding unavailable for document %s: %s. "
                        "Storing full_text only (chunks will not be retrievable via RAG).",
                        doc_id, exc,
                    )

            doc.status = DocumentStatus.READY
            await session.commit()

        except Exception as exc:  # noqa: BLE001 - background task must not raise
            logger.error("Ingestion failed for document %s: %s", doc_id, exc, exc_info=True)
            await session.rollback()
            try:
                failed = await session.get(Document, doc_id)
                if failed is not None:
                    failed.status = DocumentStatus.ERROR
                    failed.error_message = str(exc)[:_ERROR_MESSAGE_MAX]
                    await session.commit()
            except Exception as inner:  # noqa: BLE001
                logger.error("Could not mark document %s as error: %s", doc_id, inner)
