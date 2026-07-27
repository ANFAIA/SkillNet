"""One learner's pre-assessment attempt on a node.

The partial UNIQUE index over ``(user_id, node_id, schema_version) WHERE scored``
is the anti-retry rule: without it, re-entering a node ~16 times would brute-force
a 2/2 verdict on any node, including a ``critical`` safety one.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
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


class NodeProbe(UUIDMixin, Base):
    __tablename__ = "node_probes"
    __table_args__ = (
        CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 1)", name="ck_node_probes_score"
        ),
        Index(
            "uq_node_probes_user_node_version",
            "user_id",
            "node_id",
            "schema_version",
            unique=True,
            postgresql_where=text("scored"),
        ),
        Index(
            "idx_node_probes_user_node",
            "user_id",
            "node_id",
            text("created_at DESC"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_nodes.id", ondelete="CASCADE"), nullable=False
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_no: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("1"), default=1
    )
    items: Mapped[list] = mapped_column(JSONB, nullable=False)
    answer_key: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    answers: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    score: Mapped[float | None] = mapped_column(REAL, nullable=True)
    mastered: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tiebreak_used: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    # scored=false: the novice diagnostic probe, and superseded re-probe attempts.
    scored: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), default=True
    )
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
