"""SourceImage model — one image found *inside* a customer's own source document.

Not a generated asset. ``media_artifacts`` holds what the model invented; this table
holds what the organization already had: the real machine photo, the real form, the real
wiring diagram embedded in the PDF somebody uploaded. For a maintenance manual or a
compliance procedure that picture beats anything an image model can draw, and until now
ingestion decoded it and threw it away.

Every column that is not the bytes is provenance, and that is the point. Reusing a
customer's own diagram in a course is only defensible if the course can say where it came
from, so the row carries what a caption needs — the document it belongs to, the ``page``
it sat on and the ``heading`` of the section that covers that page. Those are exactly the
three fields :meth:`src.services.media.grounding.GroundedPassage.marker` renders
(``[Fuente cN: Title > Section, pag. P]``), so a reused image cites in the same dialect as
a reused passage rather than inventing a second one.

``description`` is nullable on purpose. Storing the bytes needs nothing but pdfplumber;
describing them needs a vision model (``VISION_MODEL``), which is unset by default. The
image is kept either way — a missing description is a caption the next pass can ask for
later, whereas discarded bytes are gone with the upload.

``is_decorative`` is the deterministic junk filter's verdict, decided once at ingest by
cheap rules (see :mod:`src.services.source_images`) and never at render time. Furniture —
the logo in every page header, the rule under every title — is marked rather than dropped,
because the rules are heuristics and a human overriding one should not require re-ingesting
the document. The rows are cheap: the store is content-addressed, so a logo repeated on
forty pages is one file.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UUIDMixin


class SourceImage(UUIDMixin, Base):
    __tablename__ = "source_images"
    __table_args__ = (
        # The listing every consumer performs: this document's images, in reading order.
        Index("idx_source_images_document", "document_id", "page"),
        # The dedup/lookup key, and what the asset route rebuilds its path from.
        Index("idx_source_images_content_hash", "content_hash"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    #: 1-based, matching ``ParsedSection.page_start`` and the ``pag. N`` a citation prints.
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Heading of the section covering ``page``. Empty string when the document has none.
    heading: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    #: sha256 of the stored bytes: the dedup key and the file stem.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Where the bytes live on disk (``SOURCE_IMAGES_DIR/{org}/{document}/{hash}.{ext}``).
    asset_path: Mapped[str] = mapped_column(Text, nullable=False)
    #: Source pixel dimensions, as declared by the PDF. Feed the decorative rules and let a
    #: renderer reserve the right box before the bytes arrive.
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    #: What a vision model saw. NULL whenever no vision model was configured.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_decorative: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
