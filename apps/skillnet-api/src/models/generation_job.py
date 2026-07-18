"""Generation job model (tracks the LangGraph content pipeline)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, UUIDMixin


class GenerationOutput(str, enum.Enum):
    COURSE_AND_MANUAL = "course_and_manual"
    MANUAL_ONLY = "manual_only"


class GenerationStep(str, enum.Enum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    STRUCTURING = "structuring"
    GENERATING = "generating"
    REVIEWING = "reviewing"
    PUBLISHED = "published"
    FAILED = "failed"


class GenerationJob(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "generation_jobs"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    triggered_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    output_type: Mapped[GenerationOutput] = mapped_column(
        SAEnum(
            GenerationOutput,
            name="generation_output",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    status: Mapped[GenerationStep] = mapped_column(
        SAEnum(
            GenerationStep,
            name="generation_step",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=GenerationStep.PENDING,
    )
    langgraph_thread_id: Mapped[str | None] = mapped_column(String, nullable=True)
    progress: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    result_course_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("courses.id"), nullable=True
    )
    # No manuals table in v1: kept as a plain nullable column, unused.
    result_manual_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
