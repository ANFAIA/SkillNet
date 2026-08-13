"""Append-only interaction log feeding ``learner_profiles.format_vector``.

Privacy: ``metadata`` never stores user text nor copied content. Node instrumentation
stores only ``element_id``/``ms``; Didact instrumentation stores only its validated
coordinates and bounded telemetry envelope. Retention is 90 days, purged by
``python -m src.scripts.purge_learning_data``.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, REAL, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UUIDMixin


class LearningEvent(UUIDMixin, Base):
    __tablename__ = "learning_events"
    __table_args__ = (
        Index("idx_learning_events_user", "user_id", text("created_at DESC")),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("course_nodes.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    # One of the four format_vector dimensions: texto | ejercicio | codigo | dato.
    element: Mapped[str | None] = mapped_column(Text, nullable=True)
    weight: Mapped[float] = mapped_column(
        REAL, nullable=False, server_default=text("0"), default=0.0
    )
    # `metadata` is reserved on declarative classes, so map the column explicitly.
    event_metadata: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
