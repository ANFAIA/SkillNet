"""Immutable, grounded learning material prepared for one course-node snapshot.

``NodeKnowledgePackRecord`` deliberately sits *between* the course graph and a future
on-the-fly OpenUI adapter. It is not a learner render and it has no ``user_id``: a pack
is reusable source material from which several learner experiences may be composed.

Snapshots are identified by ``(node_id, source_fingerprint, generator_version)``. When the
source changes, the old row is marked ``stale`` instead of being overwritten. That prevents
a slow worker, started against an old source snapshot, from publishing as the new course.
"""

import enum
import uuid

from sqlalchemy import (
    CheckConstraint,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, UUIDMixin


class NodeKnowledgePackStatus(str, enum.Enum):
    """Lifecycle of one immutable source snapshot."""

    PENDING = "pending"
    READY = "ready"
    REVIEW_REQUIRED = "review_required"
    STALE = "stale"
    FAILED = "failed"


class NodeKnowledgePackRecord(UUIDMixin, TimestampMixin, Base):
    """A prepared Markdown dossier and machine-readable atoms for one node."""

    __tablename__ = "node_knowledge_packs"
    __table_args__ = (
        UniqueConstraint(
            "node_id",
            "source_fingerprint",
            "generator_version",
            name="uq_node_knowledge_packs_snapshot",
        ),
        CheckConstraint(
            "status NOT IN ('ready', 'review_required') OR ("
            "markdown IS NOT NULL AND markdown_hash IS NOT NULL "
            "AND pack_hash IS NOT NULL AND jsonb_typeof(pack_payload) = 'object')",
            name="ck_node_knowledge_packs_ready_payload",
        ),
        Index("idx_node_knowledge_packs_node", "node_id", text("created_at DESC")),
        Index("idx_node_knowledge_packs_status", "status"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_nodes.id", ondelete="CASCADE"), nullable=False
    )
    # Hash of node metadata and the grounded source material used to build this pack.
    source_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    # Version of the pack contract/prompt, not the user-facing OpenUI prompt version.
    generator_version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[NodeKnowledgePackStatus] = mapped_column(
        SAEnum(
            NodeKnowledgePackStatus,
            name="node_knowledge_pack_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        server_default=NodeKnowledgePackStatus.PENDING.value,
        default=NodeKnowledgePackStatus.PENDING,
    )
    # Human-reviewable dossier. NULL until a worker has completed successfully.
    markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Atoms are selected by a future adapter; provenance maps them back to source passages.
    atoms: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    # Canonical, complete contract payload. ``atoms`` is retained as a compact
    # inspection/indexing view; runtime selection must reconstruct from this object,
    # never by parsing the human-readable Markdown.
    pack_payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    provenance: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    markdown_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    atoms_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    pack_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
