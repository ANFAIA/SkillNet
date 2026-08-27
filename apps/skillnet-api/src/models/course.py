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


class CourseTutorStyle(str, enum.Enum):
    """How the learner tutor answers questions inside this course.

    ``SOCRATIC`` asks a guiding question before giving the answer;
    ``DIRECT`` answers plainly. Auto-detected by the schema designer at
    creation time (``src/agents/schema/nodes.py``), editable afterward like
    any other course setting.
    """

    SOCRATIC = "socratic"
    DIRECT = "direct"


class CourseImageSourcePolicy(str, enum.Enum):
    """What this course does with the images that were inside its source document.

    The default rule (``AUTO``) is *diagrams get rebuilt, screenshots get kept*. A
    screenshot's information is spatial — where a control sits on a screen — and prose
    is strictly worse than the picture, so the original is placed. A conceptual diagram
    is usually better as interactive SkillNet content than as a photograph of a diagram,
    so its description is handed to the generator to re-express with the kit. An image
    nothing classified (``source_images.kind == 'unknown'``, which is what you get with
    no vision model) is **kept**: nothing can be rebuilt from a description that was
    never made.

    The two overrides exist because the rule is a heuristic and some answers are
    policy, not judgement:

    * ``KEEP_ORIGINAL`` — "do not invent anything, show my material". A compliance
      requirement no heuristic can serve.
    * ``REBUILD`` — everything in SkillNet's own visual language; the source image is
      never placed, only described to the generator.

    Not asked at course creation on purpose: the rule decides and nobody has to choose.
    It lives in the course settings, editable afterwards like ``tutor_style``.
    """

    AUTO = "auto"
    KEEP_ORIGINAL = "keep_original"
    REBUILD = "rebuild"


class CourseGenerationState(str, enum.Enum):
    """Whether a creation run owns this course, and how the last one ended.

    Orthogonal to ``status`` and ``schema_status``, which describe the course; this
    describes the *run* that was supposed to finish it. Creating a v2 course means
    "wait for the knowledge packs, review the graph, validate it", and that sequence
    used to be driven from the browser tab — a tab that closed mid-way left a row that
    looked exactly like a deliberate draft. ``IN_PROGRESS`` says a server task owns it,
    ``FAILED`` says a run died (with a reason in ``generation_error``), ``COMPLETE``
    says one finished. ``IDLE`` is the default and means nothing is claimed: every
    course made before this column existed, and every course made by hand.
    """

    IDLE = "idle"
    IN_PROGRESS = "in_progress"
    FAILED = "failed"
    COMPLETE = "complete"


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
    tutor_style: Mapped[CourseTutorStyle] = mapped_column(
        SAEnum(
            CourseTutorStyle,
            name="course_tutor_style",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=CourseTutorStyle.SOCRATIC.value,
        default=CourseTutorStyle.SOCRATIC,
    )
    # What this course does with the images embedded in its source document
    # (migration 0028). ``auto`` is the rule; the two overrides are policy escapes.
    image_source_policy: Mapped[CourseImageSourcePolicy] = mapped_column(
        SAEnum(
            CourseImageSourcePolicy,
            name="course_image_source_policy",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=CourseImageSourcePolicy.AUTO.value,
        default=CourseImageSourcePolicy.AUTO,
    )
    # --- creation-run bookkeeping (migration 0025) ---
    generation_state: Mapped[CourseGenerationState] = mapped_column(
        SAEnum(
            CourseGenerationState,
            name="course_generation_state",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=CourseGenerationState.IDLE.value,
        default=CourseGenerationState.IDLE,
    )
    # A short, safe sentence — never a raw exception. See ``course_finalization``.
    generation_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    generation_failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
