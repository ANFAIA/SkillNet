"""One graded item attempt inside a v2 node.

Separate from ``exercise_attempts`` because that table requires
``exercise_id NOT NULL REFERENCES exercises(id)`` and items generated on the fly
are not rows of ``exercises``. The ``exercise_type`` enum *is* reused, and so is
the deterministic grader ``src.services.exercise_service.grade``.
"""

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
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UUIDMixin
from src.models.exercise import ExerciseType

BLOOM_LEVELS: tuple[str, ...] = (
    "remember",
    "understand",
    "apply",
    "analyze",
    "evaluate",
    "create",
)


class NodeAttempt(UUIDMixin, Base):
    __tablename__ = "node_attempts"
    __table_args__ = (
        CheckConstraint(
            "bloom_level IN ('remember','understand','apply','analyze','evaluate','create')",
            name="ck_node_attempts_bloom_level",
        ),
        CheckConstraint("score >= 0 AND score <= 1", name="ck_node_attempts_score"),
        Index(
            "idx_node_attempts_user_node",
            "user_id",
            "node_id",
            text("attempted_at DESC"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_nodes.id", ondelete="CASCADE"), nullable=False
    )
    render_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("node_renders.id", ondelete="SET NULL"), nullable=True
    )
    probe_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("node_probes.id", ondelete="SET NULL"), nullable=True
    )
    item_id: Mapped[str] = mapped_column(Text, nullable=False)
    item_type: Mapped[ExerciseType] = mapped_column(
        SAEnum(
            ExerciseType,
            name="exercise_type",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    bloom_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer: Mapped[dict] = mapped_column(JSONB, nullable=False)
    score: Mapped[float] = mapped_column(REAL, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    hints_used: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0"), default=0
    )
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
