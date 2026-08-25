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


def _safe_error_message(exc: Exception) -> str:
    """Return a user-facing error message that never exposes raw SQL or stack traces.

    Known error patterns are mapped to friendly messages. Anything unrecognised
    is replaced with a generic sentence so internal details never leak.
    """
    raw = str(exc)
    lower = raw.lower()
    if "dimension" in lower or "expected" in lower and "got" in lower:
        return "Error processing document: embedding dimension mismatch. Check that the embedding model matches the database schema."
    if "does not exist" in lower and ("relation" in lower or "table" in lower):
        return "Error processing document: database table not found. Run migrations first."
    if "duplicate key" in lower:
        return "Error processing document: duplicate record detected."
    if "connect" in lower or "connection" in lower:
        return "Error processing document: database connection failed."
    # Generic fallback — no raw SQL leaks.
    return "Error processing document. Check the server logs for details."


def _decode_pdf_image(img: dict) -> bytes | None:
    """Return real PNG/JPEG-encoded bytes for one ``page.images[i]`` entry, or ``None``.

    There is no ``page.extract_image()`` on the installed pdfplumber (0.11.x) — the
    correct way to reach the pixel data is the image dict's own ``stream``. That data has
    already run through the PDF filter chain, so a ``DCTDecode`` (JPEG) image comes back
    as real, already-encoded JPEG bytes; a ``FlateDecode`` one (the common case for
    screenshots) comes back as *raw, uncompressed pixels* with no file header at all —
    handing those straight to a vision model is not a decodable image. Reconstruct that
    case with PIL from the dict's own ``srcsize``/``colorspace`` before re-encoding as PNG.
    """
    raw = img["stream"].get_data()
    if raw[:4] == b"\x89PNG" or raw[:2] == b"\xff\xd8":
        return raw

    try:
        import io

        from PIL import Image
    except ImportError:
        return None

    width, height = img.get("srcsize") or (None, None)
    if not width or not height:
        return None

    colorspace = img.get("colorspace")
    first = colorspace[0] if isinstance(colorspace, list) and colorspace else colorspace
    mode = "RGB"
    if first in ("/DeviceGray", "DeviceGray", "/CalGray", "CalGray"):
        mode = "L"
    elif first in ("/DeviceCMYK", "DeviceCMYK"):
        mode = "CMYK"
    channels = {"RGB": 3, "L": 1, "CMYK": 4}[mode]

    expected = width * height * channels
    if len(raw) < expected:
        return None

    try:
        pil_image = Image.frombytes(mode, (width, height), raw[:expected])
        if mode == "CMYK":
            pil_image = pil_image.convert("RGB")
        buf = io.BytesIO()
        pil_image.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:  # noqa: BLE001 - a stream this module can't decode is not fatal
        return None


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
                        image_bytes = _decode_pdf_image(img)
                        if image_bytes is None or len(image_bytes) < MIN_IMAGE_BYTES:
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
                    failed.error_message = _safe_error_message(exc)[:_ERROR_MESSAGE_MAX]
                    await session.commit()
            except Exception as inner:  # noqa: BLE001
                logger.error("Could not mark document %s as error: %s", doc_id, inner)
