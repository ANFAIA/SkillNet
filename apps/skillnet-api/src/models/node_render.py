"""Node render model — a runtime-generated UI spec for a course node (v2).

``node_renders`` has **no** ``user_id``: the row is shared by every learner whose
profile hashes to the same ``cache_key``. ``generated_by`` records who paid for
the generation; read auditing lives in ``node_render_views``.
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
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UUIDMixin


class UiFormat(str, enum.Enum):
    """Canonical UI formats. ``SIMULATION`` is reserved and never emitted (see §1.3)."""

    EXPLANATION = "explanation"
    SIMULATION = "simulation"
    EXERCISE = "exercise"
    CHART = "chart"
    MIXED = "mixed"


class NodeRenderStatus(str, enum.Enum):
    PENDING = "pending"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"
    FALLBACK = "fallback"


class NodeRender(UUIDMixin, Base):
    __tablename__ = "node_renders"
    __table_args__ = (
        UniqueConstraint("cache_key", name="uq_node_renders_cache_key"),
        CheckConstraint("tier IN ('fast', 'heavy')", name="ck_node_renders_tier"),
        Index("idx_node_renders_node", "node_id", text("created_at DESC")),
        Index("idx_node_renders_status", "status"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    generated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_preview: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_nodes.id", ondelete="CASCADE"), nullable=False
    )
    cache_key: Mapped[str] = mapped_column(Text, nullable=False)
    ui_format: Mapped[UiFormat] = mapped_column(
        SAEnum(
            UiFormat,
            name="ui_format",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    ui_spec: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    # Never serialized to the API. Structural equivalent of v1's strip_answers().
    answer_key: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    raw_dsl: Mapped[str | None] = mapped_column(Text, nullable=True)
    backend: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[NodeRenderStatus] = mapped_column(
        SAEnum(
            NodeRenderStatus,
            name="node_render_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=NodeRenderStatus.PENDING.value,
        default=NodeRenderStatus.PENDING,
    )
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
