"""Per-(user, node) mastery state.

``mastery`` (real 0..1) is the single primary scale; Shu-Ha-Ri, ``skill_level``
and the target Bloom level are derived in code and never persisted twice.
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
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UUIDMixin, aware_utc_now


class NodeState(str, enum.Enum):
    """``NEEDS_REVIEW``'s only producer in this PR is the hint ceiling of §7.4."""

    NOT_STARTED = "not_started"
    PROBING = "probing"
    LEARNING = "learning"
    MASTERED = "mastered"
    NEEDS_REVIEW = "needs_review"


class ErrorKind(str, enum.Enum):
    DETAIL = "detail"
    PROCEDURAL = "procedural"
    CONCEPTUAL = "conceptual"


SCAFFOLD_BANDS: tuple[str, ...] = ("novice", "neutral", "advanced")


class LearnerNodeState(UUIDMixin, Base):
    __tablename__ = "learner_node_states"
    __table_args__ = (
        CheckConstraint("mastery >= 0 AND mastery <= 1", name="ck_lns_mastery"),
        CheckConstraint(
            "probe_score IS NULL OR (probe_score >= 0 AND probe_score <= 1)",
            name="ck_lns_probe_score",
        ),
        CheckConstraint(
            "scaffold_band IN ('novice','neutral','advanced')",
            name="ck_lns_scaffold_band",
        ),
        UniqueConstraint("user_id", "node_id", name="uq_lns_user_node"),
        Index("idx_lns_user", "user_id"),
        Index("idx_lns_state", "user_id", "state"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_nodes.id", ondelete="CASCADE"), nullable=False
    )
    state: Mapped[NodeState] = mapped_column(
        SAEnum(
            NodeState,
            name="node_state",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=NodeState.NOT_STARTED.value,
        default=NodeState.NOT_STARTED,
    )
    mastery: Mapped[float] = mapped_column(
        REAL, nullable=False, server_default=text("0"), default=0.0
    )
    probe_score: Mapped[float | None] = mapped_column(REAL, nullable=True)
    consecutive_correct: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0"), default=0
    )
    consecutive_failed: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0"), default=0
    )
    hints_used: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0"), default=0
    )
    attempts_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    last_error_kind: Mapped[ErrorKind | None] = mapped_column(
        SAEnum(
            ErrorKind,
            name="error_kind",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=True,
    )
    # Vision A: the render is pinned when the node is opened; no cache_key recompute.
    active_render_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("node_renders.id", ondelete="SET NULL"), nullable=True
    )
    render_pinned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), default=True
    )
    pinned_personalization_revision: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    # Computed once, when the probe closes. Stable for the whole node by construction.
    scaffold_band: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="neutral", default="neutral"
    )
    waived_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    waived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    mastered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: When the learner reached the end of the node's content (migration 0029).
    #:
    #: **A separate dimension from mastery, on purpose.** ``mastered_at`` records a
    #: demonstration (rule 6 of §7.3: a streak of correct graded answers); this records
    #: that the material was worked through. An expository node has no graded item, so it
    #: can never be ``mastered`` and without this column it counted as zero progress
    #: forever. Neither implies the other: a node can be finished without being mastered,
    #: and mastered without its last screen being reached.
    #:
    #: Not ``first_seen_at``'s twin either — that one is stamped when the render is
    #: *served*, so it says "opened", not "finished". Written only by
    #: ``POST /nodes/{id}/complete`` via ``LearnerNodeStateRepository.mark_completed``,
    #: and, like ``first_seen_at``, never moved once set.
    #:
    #: No ``onupdate``: this is an event stamp, not a row-touch stamp.
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: A Python callable, never ``text("now()")``: a SQL expression puts the column in
    #: the UPDATE's ``postfetch`` set and expires the attribute, so the first read after
    #: ``await db.commit()`` raises ``MissingGreenlet``. See ``base.aware_utc_now``.
    #: Aware, unlike the ``TimestampMixin`` default, because this column declares
    #: ``DateTime(timezone=True)``.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=aware_utc_now,
    )
