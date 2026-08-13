"""Who, besides admins, may generate course-level media for a course."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, PrimaryKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.course import Course


class CourseArtifactGenerator(Base):
    __tablename__ = "course_artifact_generators"
    __table_args__ = (
        PrimaryKeyConstraint("course_id", "user_id", name="pk_course_artifact_generators"),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    course: Mapped["Course"] = relationship(back_populates="artifact_generators")
