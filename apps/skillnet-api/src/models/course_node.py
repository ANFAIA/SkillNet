"""Course node model — the unit of a dynamic (v2) course.

Nodes coexist with v1 ``modules``/``lessons``: ``seed_lesson_id`` points at the
equivalent v1 lesson, which is the degraded-mode fallback when generation fails.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    REAL,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, UUIDMixin
from src.models.node_render import UiFormat


class NodeCriticality(str, enum.Enum):
    CRITICAL = "critical"
    RECOMMENDED = "recommended"
    CONTEXTUAL = "contextual"


# Per-node mastery threshold defaults derived from criticality (§3.2).
CRITICALITY_THRESHOLDS: dict[NodeCriticality, float] = {
    NodeCriticality.CRITICAL: 0.90,
    NodeCriticality.RECOMMENDED: 0.80,
    NodeCriticality.CONTEXTUAL: 0.70,
}


class CourseNode(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "course_nodes"
    __table_args__ = (
        CheckConstraint(
            "mastery_threshold > 0 AND mastery_threshold <= 1",
            name="ck_course_nodes_mastery_threshold",
        ),
        # Deferrable so a single PUT can swap two positions inside one transaction.
        UniqueConstraint(
            "course_id",
            "position",
            name="uq_course_nodes_position",
            deferrable=True,
            initially="IMMEDIATE",
        ),
        Index("idx_course_nodes_course", "course_id", "position"),
        Index("idx_course_nodes_skill", "skill_id"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("skills.id", ondelete="SET NULL"), nullable=True
    )
    seed_lesson_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lessons.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    # NOT NULL on purpose: the PageIndex tree the tutor reads is built from summaries.
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    criticality: Mapped[NodeCriticality] = mapped_column(
        SAEnum(
            NodeCriticality,
            name="node_criticality",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=NodeCriticality.RECOMMENDED.value,
        default=NodeCriticality.RECOMMENDED,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    # Headings, not chunk ids: chunks die on re-ingestion, headings survive.
    source_headings: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    mastery_threshold: Mapped[float] = mapped_column(
        REAL, nullable=False, server_default=text("0.80"), default=0.80
    )
    default_ui_format: Mapped[UiFormat] = mapped_column(
        SAEnum(
            UiFormat,
            name="ui_format",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=UiFormat.EXPLANATION.value,
        default=UiFormat.EXPLANATION,
    )
    # Pre-assessment pre-generated at validation time, shared by every learner.
    probe_items: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    probe_answer_key: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # A node without reviewed_at cannot be served (409 node_not_reviewed).
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
