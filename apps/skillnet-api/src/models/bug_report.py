"""A problem a person reports from inside the app.

The row is written first, before the model judges it or GitHub hears of it, so a report is
never lost when either fails. ``status`` says where it ended up.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UUIDMixin

#: pending: waiting to be judged, or judged and waiting for an admin because GitHub is not
#: set up. issue: filed. discarded: judged not genuine. failed: the model or GitHub failed.
BUG_REPORT_STATUSES: tuple[str, ...] = ("pending", "issue", "discarded", "failed")


class BugReport(UUIDMixin, Base):
    __tablename__ = "bug_reports"
    __table_args__ = (
        Index("idx_bug_reports_user", "user_id", text("created_at DESC")),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    page_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    environment: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'")
    )
    # {genuine, severity, kind, title, body, reason, duplicate_of}, or {error}.
    verdict: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    issue_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
