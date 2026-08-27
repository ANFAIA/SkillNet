"""Document ingestion orchestrator (background task).

Invoked lazily by the ``POST /documents/{id}/process`` seam. Opens its own DB
session, parses the stored file, and either stores the full text (small docs)
or chunks + embeds + persists chunks (large docs). Never raises out: any failure
marks the document ``error`` so the background task exits cleanly.

Images embedded in a PDF are **kept**: decoded, filtered by cheap deterministic rules and
written to the source-image store, whether or not a vision model is configured. Only the
*description* needs ``VISION_MODEL``; without it the images are still stored, with a NULL
description, and the document is processed text-only exactly as before. Keeping them is
what lets a course later illustrate itself with the customer's own diagram instead of an
invented one. Nothing is extracted from a ``GENERATED`` document — see
:func:`_extract_pdf_images`.
"""

from __future__ import annotations

import io
import uuid
from dataclasses import dataclass
from pathlib import Path

from src.core.logging import get_logger
from src.deps.db import async_session_factory
from src.llm.embedding import resolve_embedding_config
from src.llm.fixtures import maybe_fixture_embedder
from src.models import (
    Document,
    DocumentOrigin,
    DocumentStatus,
    Organization,
    SourceImageKind,
)
from src.repositories.document_chunk_repo import DocumentChunkRepository
from src.repositories.source_image_repo import SourceImageRepository
from src.services.chunker import chunk_sections
from src.services.document_parser import ParsedSection, parse_document
from src.services.source_images import (
    ImageCandidate,
    SourceImageStore,
    content_hash,
    decorative_flags,
    image_extension,
)

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


def _image_size(img: dict, data: bytes) -> tuple[int, int]:
    """Pixel dimensions of one image: the PDF's own ``srcsize``, or PIL as a fallback.

    ``srcsize`` is what the decoder already trusts to rebuild a FlateDecode stream, so
    when it is present it is authoritative and free. A DCTDecode (JPEG) entry can arrive
    without it, and there the encoded bytes are the only source.
    """
    size = img.get("srcsize")
    if isinstance(size, (tuple, list)) and len(size) == 2 and all(size):
        return int(size[0]), int(size[1])
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as pil_image:
            return int(pil_image.width), int(pil_image.height)
    except Exception:  # noqa: BLE001 - an unmeasurable image is skipped, not fatal
        return 0, 0


def _covering_heading(sections: list[ParsedSection], page: int) -> str:
    """Heading of the section that covers ``page``, or ``""``.

    Same walk (and same ``reversed``) the description injection below uses, so an image's
    stored ``heading`` and the section its ``[Imagen: ...]`` text lands in are always the
    same section — a caption that named a different one would be worse than none.
    """
    for section in reversed(sections):
        if section.page_start <= page <= section.page_end:
            return section.heading or ""
    return ""


@dataclass
class _ExtractedImage:
    """One stored image, between extraction and the row that records it."""

    page: int
    heading: str
    content_hash: str
    asset_path: str
    width: int
    height: int
    size_bytes: int


async def _extract_pdf_images(
    session,
    doc: Document,
    path: Path,
    sections: list[ParsedSection],
    org_settings: dict,
) -> list[ParsedSection]:
    """Keep the images embedded in a PDF, and describe the ones worth describing.

    Runs whether or not vision is configured — that is the whole change. The bytes are
    the valuable part and they used to be discarded; ``VISION_MODEL`` only decides whether
    a row also gets a ``description`` and a ``kind`` (without it every row is ``unknown``,
    which downstream means "keep the original"). Every image that clears the byte floor is stored
    and recorded; the deterministic rules in :mod:`src.services.source_images` decide
    which rows are furniture, and furniture is marked rather than dropped so a human can
    override the guess without re-ingesting the document.

    A ``GENERATED`` document is skipped outright. Its text was written by a model from a
    one-line idea, so anything found in it is by definition not the organization's own
    material, and letting it into this table would be exactly the laundering the
    ``origin`` column exists to prevent. (Today those are always ``.md`` and the PDF guard
    would catch them anyway; the check is explicit because that is a coincidence of the
    current writer, not a rule.)

    Best-effort throughout: sections come back unchanged on any failure, and the caller's
    ingestion never fails because of an image.
    """
    from src.services.image_describer import (
        MIN_IMAGE_BYTES,
        ImageDescription,
        VisionDescription,
        describe_image,
        resolve_vision_config,
    )

    if doc.origin == DocumentOrigin.GENERATED:
        return sections

    if not str(path).lower().endswith(".pdf"):
        return sections

    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber not available for image extraction")
        return sections

    store = SourceImageStore()
    repo = SourceImageRepository(session)

    # Re-ingestion replaces: the previous run's rows and files must go before this run's
    # are written, or a figure removed from the source lives on forever.
    await repo.delete_for_document(doc.id)
    store.clear_document(doc.org_id, doc.id)

    extracted: list[_ExtractedImage] = []
    page_count = 0
    try:
        with pdfplumber.open(str(path)) as pdf:
            page_count = len(pdf.pages)
            for page_num, page in enumerate(pdf.pages, 1):
                for img in page.images:
                    try:
                        image_bytes = _decode_pdf_image(img)
                        if image_bytes is None or len(image_bytes) < MIN_IMAGE_BYTES:
                            continue
                        width, height = _image_size(img, image_bytes)
                        if not width or not height:
                            continue
                        ext = image_extension(image_bytes)
                        asset_path = store.store(
                            doc.org_id, doc.id, image_bytes, ext
                        )
                        extracted.append(
                            _ExtractedImage(
                                page=page_num,
                                heading=_covering_heading(sections, page_num),
                                content_hash=content_hash(image_bytes),
                                asset_path=str(asset_path),
                                width=width,
                                height=height,
                                size_bytes=len(image_bytes),
                            )
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("Image extraction failed on page %d: %s", page_num, exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("PDF image scan failed for %s: %s", path, exc)
        return sections

    if not extracted:
        return sections

    flags = decorative_flags(
        [
            ImageCandidate(
                page=item.page,
                content_hash=item.content_hash,
                width=item.width,
                height=item.height,
            )
            for item in extracted
        ],
        page_count,
    )

    config = resolve_vision_config(org_settings)
    # One description per distinct image, not per occurrence: the store is content-
    # addressed, so the same bytes on three pages are one file and deserve one vision call.
    described: dict[str, VisionDescription] = {}
    descriptions: list[ImageDescription] = []

    for item, decorative in zip(extracted, flags, strict=True):
        seen: VisionDescription | None = None
        if config is not None and not decorative:
            if item.content_hash in described:
                seen = described[item.content_hash]
            else:
                try:
                    seen = await describe_image(store.read(item.asset_path), config)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Image description failed on page %d: %s", item.page, exc)
                    seen = None
                if seen is not None:
                    described[item.content_hash] = seen
            if seen is not None:
                descriptions.append(
                    ImageDescription(page=item.page, description=seen.text)
                )

        await repo.create(
            org_id=doc.org_id,
            document_id=doc.id,
            page=item.page,
            heading=item.heading,
            content_hash=item.content_hash,
            asset_path=item.asset_path,
            width=item.width,
            height=item.height,
            bytes=item.size_bytes,
            description=seen.text if seen is not None else None,
            # No vision model, a decorative image, or an unusable answer all land on
            # ``unknown``, which downstream reads as "cannot be rebuilt, keep the
            # original" — the same treatment a screenshot gets, and the safe one.
            kind=seen.kind if seen is not None else SourceImageKind.UNKNOWN.value,
            is_decorative=decorative,
        )

    reusable = sum(1 for flag in flags if not flag)
    logger.info(
        "Kept %d images from %s (%d reusable, %d described)",
        len(extracted), path.name, reusable, len(descriptions),
    )

    # Insert descriptions into the section that covers each image's page. Unchanged: the
    # `[Imagen: ...]` marker is what makes an image findable by RAG, and the chunker and
    # retrieval bench both depend on its shape.
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

            # Keep the images embedded in a PDF (always), and describe them if a vision
            # model is configured. Never fatal: a failure here costs the images, not the
            # document, so ingestion carries on with the text it already has.
            org = await session.get(Organization, doc.org_id)
            org_settings = dict(org.settings) if org and org.settings else {}
            try:
                sections = await _extract_pdf_images(
                    session, doc, Path(doc.storage_path), sections, org_settings,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Source image extraction failed for document %s: %s", doc_id, exc
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
