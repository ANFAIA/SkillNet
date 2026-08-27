"""Keeping the images that live inside an uploaded document, and telling junk from content.

Two things live here, and neither of them talks to a model:

* :class:`SourceImageStore` — the on-disk home for the bytes, content-addressed exactly
  like :class:`src.services.media.assets.AssetStore` (same atomic write, same "the name is
  the hash so storing twice is a no-op"). Deliberately a *separate* store: those are
  generated assets, these are the customer's own material, and the two must not share a
  lifetime — a source image dies with the document it was extracted from.

  Unlike ``AssetStore`` the tree is scoped per organization and per document
  (``{base}/{org_id}/{document_id}/{hash}.{ext}``) rather than flat. That is what makes
  deleting a document complete: one ``rmtree`` and nothing of it is left. A flat,
  globally deduplicated store would make the same delete either unsafe (another
  document's rows can point at the same bytes) or a refcount query. Dedup still happens
  where it pays — the logo repeated on forty pages of *this* document is one file.

* The decorative rules — pure functions over metadata, no bytes and no LLM. A logo in
  every page header is not content, and the cheapest moment to say so is once, at ingest,
  where the verdict is stored and can be overridden. Deciding it at render time means
  paying for it on every render and having nowhere to record a human's correction.

The rules, weakest first:

1. **Pixel floor.** Under ``MIN_IMAGE_SIDE`` on either side is an icon, a bullet or a
   signature scan, not a diagram worth showing at lesson size.
2. **Aspect guard.** Beyond ``MAX_ASPECT_RATIO`` : 1 in either direction is a rule, a
   divider or a banner strip. Nothing that teaches anything is that thin.
3. **Repeat across pages.** The highest-yield rule, and it costs nothing because the
   content hash is already computed: the same bytes on a large fraction of a document's
   pages is furniture by construction. Below ``REPEAT_MIN_PAGES`` distinct pages the rule
   stays silent — in a three-page handout "on half the pages" is one repetition, which is
   not evidence of anything.

The byte floor (``MIN_IMAGE_BYTES``, in :mod:`src.services.image_describer`) is *not* one
of these: it is applied before anything is stored, because below it there is no image to
keep — the existing loop has always dropped those and this module does not resurrect them.
"""

from __future__ import annotations

import hashlib
import math
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from src.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)

#: Under this on either side an image is an icon or a signature, not a figure.
MIN_IMAGE_SIDE = 200

#: Worse than this ratio (either orientation) is a rule, a divider or a banner strip.
MAX_ASPECT_RATIO = 8.0

#: Fraction of the document's pages the same bytes must appear on to count as furniture.
REPEAT_PAGE_FRACTION = 0.5

#: ...and never fewer than this many distinct pages, whatever the fraction works out to.
#: Two occurrences in a short document is a coincidence; three is a page header.
REPEAT_MIN_PAGES = 3

#: The only extensions ``_decode_pdf_image`` can produce, and therefore the only ones the
#: asset route will ever serve. An allow-list, not a guess from the stored path.
IMAGE_EXTENSIONS = {"png": "image/png", "jpg": "image/jpeg"}


def content_hash(data: bytes) -> str:
    """The SHA-256 hex digest used as both the dedup key and the file stem."""
    return hashlib.sha256(data).hexdigest()


def image_extension(data: bytes) -> str:
    """``png`` or ``jpg`` from the magic bytes. PNG is the fallback, as it is upstream."""
    if data[:2] == b"\xff\xd8":
        return "jpg"
    return "png"


@dataclass(frozen=True)
class ImageCandidate:
    """One decoded image and the metadata the rules need. No bytes: the rules never read them."""

    page: int
    content_hash: str
    width: int
    height: int


def is_undersized(width: int, height: int) -> bool:
    """Rule 1: below the pixel floor on either side."""
    return width < MIN_IMAGE_SIDE or height < MIN_IMAGE_SIDE


def has_extreme_aspect(width: int, height: int) -> bool:
    """Rule 2: a strip rather than a figure. A zero side counts as extreme."""
    if width <= 0 or height <= 0:
        return True
    ratio = max(width, height) / min(width, height)
    return ratio > MAX_ASPECT_RATIO


def repeat_threshold(page_count: int) -> int:
    """How many distinct pages the same bytes must occupy before they are furniture."""
    return max(REPEAT_MIN_PAGES, math.ceil(page_count * REPEAT_PAGE_FRACTION))


def repeated_hashes(candidates: list[ImageCandidate], page_count: int) -> set[str]:
    """Rule 3: the content hashes that appear on enough distinct pages to be furniture."""
    threshold = repeat_threshold(page_count)
    pages_by_hash: dict[str, set[int]] = {}
    for candidate in candidates:
        pages_by_hash.setdefault(candidate.content_hash, set()).add(candidate.page)
    return {
        digest for digest, pages in pages_by_hash.items() if len(pages) >= threshold
    }


def decorative_flags(
    candidates: list[ImageCandidate], page_count: int
) -> list[bool]:
    """Apply all three rules. Returns one verdict per candidate, in the order given.

    The whole junk filter in one pure function: metadata in, booleans out, no disk and no
    model. That is what makes it testable as arithmetic rather than as an ingestion run.
    """
    furniture = repeated_hashes(candidates, page_count)
    return [
        candidate.content_hash in furniture
        or is_undersized(candidate.width, candidate.height)
        or has_extreme_aspect(candidate.width, candidate.height)
        for candidate in candidates
    ]


class SourceImageStore:
    """Content-addressed file store for images extracted from source documents."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.base_dir = Path(base_dir or settings.SOURCE_IMAGES_DIR)

    def document_dir(self, org_id: uuid.UUID, document_id: uuid.UUID) -> Path:
        """Everything extracted from one document, and nothing else."""
        return self.base_dir / str(org_id) / str(document_id)

    def path_for(
        self, org_id: uuid.UUID, document_id: uuid.UUID, digest: str, ext: str
    ) -> Path:
        """Where these bytes live. Does not touch the disk.

        ``digest`` and ``ext`` are never user input in this codebase, but the asset route
        rebuilds a path from a stored row, so both are checked here rather than trusted:
        an anchored hex digest and an allow-listed extension cannot contain a separator,
        a ``..`` or anything else that could leave ``base_dir``.
        """
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("content hash must be a 64-character lowercase hex digest")
        if ext not in IMAGE_EXTENSIONS:
            raise ValueError(f"unsupported source image extension: {ext!r}")
        return self.document_dir(org_id, document_id) / f"{digest}.{ext}"

    def store(
        self, org_id: uuid.UUID, document_id: uuid.UUID, data: bytes, ext: str
    ) -> Path:
        """Write ``data`` under this document, deduped by content. Returns the path.

        Identical bytes already on disk are left alone — that is the dedup, and it is why
        keeping a decorative row for a logo that repeats on forty pages costs one file.
        The write is atomic (temp file in the same directory, then ``os.replace``), so a
        reader sees either the whole image or nothing.
        """
        digest = content_hash(data)
        path = self.path_for(org_id, document_id, digest, ext)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return path

        fd, tmp_path = tempfile.mkstemp(dir=str(path.parent))
        closed = False
        try:
            os.write(fd, data)
            os.close(fd)
            closed = True
            os.replace(tmp_path, str(path))
        except BaseException:
            if not closed:
                os.close(fd)
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        return path

    def read(self, path: str | Path) -> bytes:
        """Read stored bytes back. Raises ``FileNotFoundError`` if the image is gone."""
        return Path(path).read_bytes()

    def clear_document(self, org_id: uuid.UUID, document_id: uuid.UUID) -> None:
        """Remove every image extracted from one document. Best-effort, never raises.

        Called from two places that both need it to be total: re-ingestion (the rows are
        replaced, so the files must be too, or a renamed figure lingers forever) and
        document deletion (where a leftover file is a copy of customer material that
        outlived the record saying it existed).
        """
        target = self.document_dir(org_id, document_id)
        try:
            if target.exists():
                shutil.rmtree(target)
            parent = target.parent
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
        except OSError as exc:
            logger.warning(
                "Could not remove source images for document %s: %s", document_id, exc
            )


__all__ = [
    "IMAGE_EXTENSIONS",
    "MAX_ASPECT_RATIO",
    "MIN_IMAGE_SIDE",
    "REPEAT_MIN_PAGES",
    "REPEAT_PAGE_FRACTION",
    "ImageCandidate",
    "SourceImageStore",
    "content_hash",
    "decorative_flags",
    "has_extreme_aspect",
    "image_extension",
    "is_undersized",
    "repeat_threshold",
    "repeated_hashes",
]
