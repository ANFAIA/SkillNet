"""Enrollment model."""

import enum
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, UUIDMixin

if TYPE_CHECKING:
    from src.models.course import Course


class EnrollmentStatus(str, enum.Enum):
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class Enrollment(UUIDMixin, Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id", name="uq_enrollments_user_course"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id"), nullable=False
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    #: The group whose assignment created this row, when one did.
    #:
    #: Recorded now because it is the one thing about a group assignment that cannot be
    #: reconstructed later: the enrollment is an ordinary row the moment it exists, and
    #: nothing else remembers where it came from. It buys "why does this person have this
    #: course?" today, and it is the prerequisite for ever making group membership drive
    #: enrollments continuously (see docs/design/admin-library-and-talent.md).
    #:
    #: ``SET NULL``, never cascade: deleting a group must not delete training. And a row
    #: that already existed keeps whatever provenance it had — an idempotent re-assignment
    #: skips it, so the group did not create it and does not get to claim it.
    source_group_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_groups.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[EnrollmentStatus] = mapped_column(
        SAEnum(
            EnrollmentStatus,
            name="enrollment_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=EnrollmentStatus.ASSIGNED,
    )
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    course: Mapped["Course"] = relationship(back_populates="enrollments")
