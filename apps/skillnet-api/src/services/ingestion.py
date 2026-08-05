"""Document ingestion orchestrator (background task).

Invoked lazily by the ``POST /documents/{id}/process`` seam. Opens its own DB
session, parses the stored file, and either stores the full text (small docs)
or chunks + embeds + persists chunks (large docs). Never raises out: any failure
marks the document ``error`` so the background task exits cleanly.

Image descriptions (for PDFs with images) are best-effort: they require a
vision-capable model configured via ``VISION_MODEL``. When absent, images are
silently skipped and the document is processed text-only.
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
from src.services.document_parser import ParsedSection, parse_document

logger = get_logger(__name__)

_ERROR_MESSAGE_MAX = 500


async def _describe_pdf_images(
    path: Path, sections: list[ParsedSection], org_settings: dict,
) -> list[ParsedSection]:
    """Enrich sections with image descriptions from a vision model.

    Best-effort: returns sections unchanged if vision is unavailable or fails.
    Only processes PDFs (other formats have no embedded images to extract).
    """
    from src.services.image_describer import (
        MIN_IMAGE_BYTES,
        ImageDescription,
        describe_image,
        resolve_vision_config,
    )

    config = resolve_vision_config(org_settings)
    if config is None:
        return sections

    if not str(path).lower().endswith(".pdf"):
        return sections

    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber not available for image extraction")
        return sections

    descriptions: list[ImageDescription] = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                for img in page.images:
                    try:
                        extracted = page.extract_image(img)
                        if not extracted or not extracted.get("stream"):
                            continue
                        image_bytes = extracted["stream"].get_data()
                        if len(image_bytes) < MIN_IMAGE_BYTES:
                            continue
                        desc = await describe_image(image_bytes, config)
                        if desc:
                            descriptions.append(ImageDescription(page=page_num, description=desc))
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("Image extraction failed on page %d: %s", page_num, exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("PDF image scan failed for %s: %s", path, exc)
        return sections

    if not descriptions:
        return sections

    logger.info("Described %d images from %s", len(descriptions), path.name)

    # Insert descriptions into the section that covers each image's page.
    for img_desc in descriptions:
        for section in reversed(sections):
            if section.page_start <= img_desc.page <= section.page_end:
                section.content += f"\n\n[Imagen: {img_desc.description}]"
                break

    return sections


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

            # Best-effort: describe images in PDFs if a vision model is configured.
            org = await session.get(Organization, doc.org_id)
            org_settings = dict(org.settings) if org and org.settings else {}
            sections = await _describe_pdf_images(
                Path(doc.storage_path), sections, org_settings,
            )

            # Rebuild full_text preserving heading markers so focus_on_headings() works.
            if sections:
                parts = []
                for s in sections:
                    if s.heading:
                        prefix = "#" * max(s.level, 1) if s.level else "##"
                        parts.append(f"{prefix} {s.heading}\n\n{s.content}")
                    else:
                        parts.append(s.content)
                full_text = "\n\n".join(parts)

            doc.page_count = page_count
            doc.full_text = full_text

            chunks = chunk_sections(sections, doc.title)

            if chunks:
                try:
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
