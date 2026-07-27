"""End-of-node learner feedback.

``unclear`` is one of only two places where free user text lands (§3.3); it is
deleted by ``DELETE /users/me/learner-profile``.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UUIDMixin

DIFFICULTY_VALUES: tuple[str, ...] = ("easy", "ok", "hard")


class NodeFeedback(UUIDMixin, Base):
    __tablename__ = "node_feedback"
    __table_args__ = (
        CheckConstraint(
            "difficulty IN ('easy', 'ok', 'hard')", name="ck_node_feedback_difficulty"
        ),
        UniqueConstraint("user_id", "node_id", name="uq_node_feedback_user_node"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_nodes.id", ondelete="CASCADE"), nullable=False
    )
    difficulty: Mapped[str] = mapped_column(Text, nullable=False)
    unclear: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
