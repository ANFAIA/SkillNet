"""Cached click-to-explain answers (Curio).

``context_hash`` is part of the key on purpose: "Mercurio" in a chemistry node and
"Mercurio" next to "planeta" must yield different explanations. Only terms of
<=60 characters and <=4 tokens are persisted (§8.4); longer selections are served
but never written. Retention: 180 days from ``last_used_at``.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UUIDMixin

# Hard limits from §8.4 / §3.4.
TERM_MAX_LENGTH = 140
TERM_CACHEABLE_MAX_LENGTH = 60
TERM_CACHEABLE_MAX_TOKENS = 4


class TermExplanation(UUIDMixin, Base):
    __tablename__ = "term_explanations"
    __table_args__ = (
        UniqueConstraint(
            "org_id",
            "term_normalized",
            "context_hash",
            "language",
            name="uq_term_explanations_lookup",
        ),
        Index("idx_term_expl_lookup", "org_id", "term_normalized", "context_hash"),
        Index("idx_term_expl_purge", "last_used_at"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("course_nodes.id", ondelete="SET NULL"), nullable=True
    )
    term: Mapped[str] = mapped_column(Text, nullable=False)
    term_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    context_hash: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="es", default="es"
    )
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    hit_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
