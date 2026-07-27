"""Per-call LLM usage log.

Written from a single place (``log_usage()`` around the new v2 node calls). It is
the only way to settle the real fast/heavy ratio with data instead of the 90/10
hypothesis. v1 nodes are not instrumented in this PR.
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
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UUIDMixin

USE_CASES: tuple[str, ...] = (
    "decide_formato",
    "genera_ui",
    "explain",
    "probe_generate",
    "schema_design",
)


class LlmUsageLog(UUIDMixin, Base):
    __tablename__ = "llm_usage_log"
    __table_args__ = (
        CheckConstraint(
            "tier IS NULL OR tier IN ('fast','heavy')", name="ck_llm_usage_log_tier"
        ),
        Index("idx_llm_usage_case", "org_id", "use_case", text("created_at DESC")),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    use_case: Mapped[str] = mapped_column(Text, nullable=False)
    # runtime_fast | runtime_heavy | generation | eval | tutor
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ok: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
