"""User-skill association with proficiency level."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, UUIDMixin
from src.models.user import User
from src.models.skill import Skill


class SkillLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class UserSkill(UUIDMixin, Base):
    __tablename__ = "user_skills"
    __table_args__ = (UniqueConstraint("user_id", "skill_id", name="uq_user_skills_user_skill"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("skills.id"), nullable=False
    )
    level: Mapped[SkillLevel] = mapped_column(
        SAEnum(
            SkillLevel,
            name="skill_level",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=SkillLevel.LOW,
    )
    source: Mapped[str] = mapped_column(String, nullable=False, default="checkpoint")
    # Timezone-aware (0006): both writers — `SkillService.record_mastery` and
    # `EnrollmentService._grant_course_skills` — assign `datetime.now(timezone.utc)`,
    # and asyncpg rejects an aware value for a naive column outright.
    last_assessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), onupdate=text("now()")
    )

    user: Mapped["User"] = relationship()
    skill: Mapped["Skill"] = relationship()
