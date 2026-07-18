"""Chat session model."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from src.models.chat_message import ChatMessage


class ChatSession(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (
        CheckConstraint(
            "agent_type IN ('tutor', 'admin')", name="ck_chat_sessions_agent_type"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    agent_type: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_covers_until: Mapped[int] = mapped_column(
        Integer, server_default=text("0")
    )
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("courses.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )
