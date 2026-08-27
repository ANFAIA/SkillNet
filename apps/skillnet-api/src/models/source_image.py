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

``kind`` is the *other* verdict, and unlike ``is_decorative`` no rule over metadata can
reach it — it takes a model that has looked at the pixels. It exists because the
rendering decision is made from it: a ``screenshot`` must be shown as it is, since its
information is spatial ("the button in the top right corner") and every prose rewrite of
that is worse than the picture; a ``diagram`` or a ``photo`` can usually be re-expressed
as something the learner can touch. ``unknown`` is the honest answer whenever nobody
looked — no ``VISION_MODEL`` (the default), a decorative image, or a model that ignored
the requested format — and downstream it reads exactly like ``screenshot``: keep the
original. That asymmetry is deliberate. Keeping an image that could have been rebuilt
costs some screen space; rebuilding one that should have been kept silently deletes what
the manual was saying.

``is_decorative`` is the deterministic junk filter's verdict, decided once at ingest by
cheap rules (see :mod:`src.services.source_images`) and never at render time. Furniture —
the logo in every page header, the rule under every title — is marked rather than dropped,
because the rules are heuristics and a human overriding one should not require re-ingesting
the document. The rows are cheap: the store is content-addressed, so a logo repeated on
forty pages is one file.
"""

import enum
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


class SourceImageKind(str, enum.Enum):
    """What the picture is, which is what decides how it may be used.

    The only distinction that has to be reliable is ``SCREENSHOT`` against the rest.
    Everything else is a refinement: a diagram and a photo are both "material a lesson
    may rebuild", they just rebuild differently.

    Stored as plain text (see migration ``0027``), not a PostgreSQL enum: the vocabulary
    is expected to grow, and a value nobody here recognises must degrade to
    :attr:`UNKNOWN` rather than raise on the way out of the database.
    """

    #: A user-interface capture. Its information is *where things are on screen*, so it
    #: is shown as it is and never paraphrased.
    SCREENSHOT = "screenshot"
    #: Flowchart, schema, conceptual drawing. Re-expressible as interactive content.
    DIAGRAM = "diagram"
    #: A real thing photographed: a machine, a place, a paper document.
    PHOTO = "photo"
    #: Nobody looked, or the answer was unusable. Treated like :attr:`SCREENSHOT`
    #: downstream — cannot be rebuilt, keep the original.
    UNKNOWN = "unknown"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)


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
    #: One of :class:`SourceImageKind`. ``"unknown"`` whenever nothing classified it —
    #: no vision model, a decorative image, or an answer that ignored the format.
    kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=SourceImageKind.UNKNOWN.value,
        default=SourceImageKind.UNKNOWN.value,
    )
    is_decorative: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
