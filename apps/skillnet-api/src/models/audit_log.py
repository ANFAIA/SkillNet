"""Administrative audit trail for schema validation, waivers and deletions.

``detail`` on ``course_schema_validated`` stores the proposed -> validated diff
(nodes added, deleted, fields edited), so it is measurable whether creators really
edit what the LLM proposes.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UUIDMixin

AUDIT_ACTIONS: tuple[str, ...] = (
    "course_schema_validated",
    "course_schema_unvalidated",
    "node_waived",
    # The only action whose subject no longer exists once it is recorded. Deleting a
    # course is now allowed in any status and with people enrolled in it, so the row
    # here is the only thing left saying who removed what, and how much training went
    # with it: `detail` carries the title, the status it had, and the enrollment counts.
    "course_deleted",
)


class AuditLog(UUIDMixin, Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("idx_audit_log_subject", "org_id", "subject", text("created_at DESC")),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    # "course:{uuid}" | "node:{uuid}"
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
