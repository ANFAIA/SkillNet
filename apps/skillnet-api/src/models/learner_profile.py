"""Learner profile model — the *declared* half of the v2 learner profile.

Three independent sources, three places: declared (here), inferred
(``learning_events`` → ``format_vector``) and by competence
(``learner_node_states``). Private to the employee; the admin only sees k>=5
aggregates.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, UUIDMixin
from src.models.user import LearningProfile

# Dimensions of ``format_vector`` — exactly what the frozen UI kit can emit (§5.3).
FORMAT_VECTOR_DIMENSIONS: tuple[str, ...] = ("texto", "ejercicio", "codigo", "dato")

EMPTY_FORMAT_VECTOR = '{"texto":0,"ejercicio":0,"codigo":0,"dato":0}'

#: The same literal, safe to interpolate into :func:`sqlalchemy.text`. ``text()`` reads
#: ``:word`` as a bind parameter and ``"texto":0`` matches, so the unescaped form
#: compiled to ``{"texto"NULL,...}`` and ``CREATE TABLE learner_profiles`` failed on a
#: real Postgres. ``\:`` is ``text()``'s own escape and comes back out as a plain colon.
_EMPTY_FORMAT_VECTOR_SQL = EMPTY_FORMAT_VECTOR.replace(":", r"\:")


class LearnerExperience(str, enum.Enum):
    """``UNKNOWN`` is the default: it maps to *neutral* scaffolding, not novice."""

    UNKNOWN = "unknown"
    NONE = "none"
    SOME = "some"
    EXPERIENCED = "experienced"


class LearnerProfile(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "learner_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_learner_profiles_user"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # role_title and sector DO travel to the LLM; goal does NOT (§3.3).
    role_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    sector: Mapped[str | None] = mapped_column(Text, nullable=True)
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    experience_level: Mapped[LearnerExperience] = mapped_column(
        SAEnum(
            LearnerExperience,
            name="learner_experience",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=LearnerExperience.UNKNOWN.value,
        default=LearnerExperience.UNKNOWN,
    )
    # Reuses the existing ``learning_profile`` enum; no new enum is created.
    preset: Mapped[LearningProfile] = mapped_column(
        SAEnum(
            LearningProfile,
            name="learning_profile",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=LearningProfile.STANDARD.value,
        default=LearningProfile.STANDARD,
    )
    format_vector: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text(f"'{_EMPTY_FORMAT_VECTOR_SQL}'::jsonb"),
    )
    format_vector_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Denormalized on purpose: read on every decide_formato, +1 only on learning -> mastered.
    nodes_completed: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    # Controlled vocabulary only (see LearnerProfileService.apply_signals). Never LLM prose.
    tutor_notes: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    onboarding_skipped: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    onboarding_version: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("1"), default=1
    )
