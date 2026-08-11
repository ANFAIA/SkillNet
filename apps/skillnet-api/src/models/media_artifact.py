"""MediaArtifact model — one NotebookLM-style rich-media output for a course/node.

The shared spine of the media pipeline (roadmap §2, build-order item #1). Every rich
artifact — podcast, slide deck, infographic, narrated-slides video, mind map, report,
cover image — is one row here, generated asynchronously and served the same way, so the
whole family inherits NotebookLM's "background, non-blocking" contract for free.

Three fields carry the grounding/provenance the roadmap insists on:

* ``spec_json`` — the grounded JSON spec the generator produced (dialogue turns, slides,
  sections...), each element carrying the ``citation_id`` of the passage it came from. This
  is what a later revision edits and what the parallel citations panel reads.
* ``asset_path`` — where the rendered bytes live in the on-disk asset store, keyed by
  ``content_hash`` (dedup). ``NULL`` for spec-only artifacts (a mind map is an explicit
  tree serialized in ``spec_json``, not a file) and while the row is still pending.
* ``content_hash`` — the sha256 of the stored bytes, so an identical render is never
  written twice and the asset route can be cached hard.

Like ``node_renders`` the row is org-scoped rather than per-user: a course-level artifact
is shared by everyone in the organization, and ``org_id`` is the scoping predicate every
route uses (defence in depth over the ``course_id`` join).
"""

import enum
import uuid

from sqlalchemy import (
    Enum as SAEnum,
    ForeignKey,
    Index,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, UUIDMixin


class MediaKind(str, enum.Enum):
    """The rich-media artifacts imitated from NotebookLM's Studio panel (roadmap §1)."""

    PODCAST = "podcast"
    SLIDES = "slides"
    INFOGRAPHIC = "infographic"
    VIDEO = "video"
    MINDMAP = "mindmap"
    REPORT = "report"
    COVER_IMAGE = "cover_image"


class MediaArtifactStatus(str, enum.Enum):
    """Lifecycle of one generation job. The runner walks pending -> running -> done|error."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class MediaArtifact(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "media_artifacts"
    __table_args__ = (
        Index("idx_media_artifacts_course", "course_id", text("created_at DESC")),
        Index("idx_media_artifacts_status", "status"),
        # The dedup lookup: an identical render (same bytes) is reused, not regenerated.
        Index("idx_media_artifacts_content_hash", "content_hash"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("course_nodes.id", ondelete="CASCADE"), nullable=True
    )
    kind: Mapped[MediaKind] = mapped_column(
        SAEnum(
            MediaKind,
            name="media_kind",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    status: Mapped[MediaArtifactStatus] = mapped_column(
        SAEnum(
            MediaArtifactStatus,
            name="media_artifact_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=MediaArtifactStatus.PENDING.value,
        default=MediaArtifactStatus.PENDING,
    )
    # The grounded JSON spec the generator produced. Empty until the job runs; carries the
    # per-element citation_ids the parallel citations panel reads.
    spec_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    # Where the rendered bytes live in the on-disk asset store. NULL for spec-only
    # artifacts and while pending/running.
    asset_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    # sha256 of the stored bytes: the dedup key. NULL when there are no bytes.
    content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Failure detail, surfaced to the admin. NULL unless status is 'error'.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
