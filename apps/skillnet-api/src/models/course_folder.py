"""Flat administrator folders used to organise the course library."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from src.models.course import Course


class CourseFolder(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "course_folders"
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    courses: Mapped[list["Course"]] = relationship(back_populates="folder")
