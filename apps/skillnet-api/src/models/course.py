"""Course model."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from src.models.course_artifact_generator import CourseArtifactGenerator
    from src.models.course_folder import CourseFolder
    from src.models.enrollment import Enrollment
    from src.models.module import Module


class ContentStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class CourseDeliveryMode(str, enum.Enum):
    """``STATIC`` = the untouched v1 path. ``DYNAMIC`` = the v2 path."""

    STATIC = "static"
    DYNAMIC = "dynamic"


class CourseSchemaStatus(str, enum.Enum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    VALIDATED = "validated"
    ARCHIVED = "archived"


class ArtifactGeneratePolicy(str, enum.Enum):
    """Who may generate course-level overviews (podcast, video, slides, infographic)."""

    ADMIN = "admin"
    EVERYONE = "everyone"
    SELECTED = "selected"


class Course(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "courses"
    __table_args__ = (
        CheckConstraint(
            "intent_density BETWEEN 1 AND 5", name="ck_courses_intent_density"
        ),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("course_folders.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    # A pre-baked onboarding demo course, seeded per-org at setup time (no LLM). Marks the
    # course so the seed is idempotent and so it can be told apart from real content.
    is_demo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    status: Mapped[ContentStatus] = mapped_column(
        SAEnum(
            ContentStatus,
            name="content_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=ContentStatus.DRAFT,
    )

    # --- v2 dynamic courses (all additive, all defaulted) ---
    delivery_mode: Mapped[CourseDeliveryMode] = mapped_column(
        SAEnum(
            CourseDeliveryMode,
            name="course_delivery_mode",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=CourseDeliveryMode.STATIC.value,
        default=CourseDeliveryMode.STATIC,
    )
    schema_status: Mapped[CourseSchemaStatus] = mapped_column(
        SAEnum(
            CourseSchemaStatus,
            name="course_schema_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=CourseSchemaStatus.DRAFT.value,
        default=CourseSchemaStatus.DRAFT,
    )
    schema_validated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    schema_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Bumped by every PUT /courses/{id}/schema that changes nodes; part of cache_key.
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1"), default=1
    )
    # Intent slider: 1 = condensed, 5 = expanded. A length budget, not a format choice.
    intent_density: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("3"), default=3
    )
    artifact_generate_policy: Mapped[ArtifactGeneratePolicy] = mapped_column(
        SAEnum(
            ArtifactGeneratePolicy,
            name="artifact_generate_policy",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=ArtifactGeneratePolicy.ADMIN.value,
        default=ArtifactGeneratePolicy.ADMIN,
    )

    modules: Mapped[list["Module"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="Module.position",
    )
    enrollments: Mapped[list["Enrollment"]] = relationship(back_populates="course")
    folder: Mapped["CourseFolder | None"] = relationship(back_populates="courses")
    artifact_generators: Mapped[list["CourseArtifactGenerator"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
    )
