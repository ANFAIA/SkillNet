"""Named lists of people, used to assign training to several at once.

A group is the audience-side counterpart of :class:`~src.models.course_folder.CourseFolder`:
flat, scoped to one organization, and deliberately without powers of its own. It grants no
permissions, organizes no content and does not nest. See
``docs/design/admin-library-and-talent.md`` for why assignment to a group is a snapshot
rather than a live subscription.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from src.models.user import User


class UserGroup(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "user_groups"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    members: Mapped[list["UserGroupMember"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class UserGroupMember(UUIDMixin, Base):
    """One person's membership of one group.

    Its own table rather than an array column on ``users``: membership has to be
    counted, filtered and joined in SQL (``GET /users?group_id=``, the member count on
    every group row), and an array can do none of those without a scan.

    Both foreign keys cascade. Deleting a group removes its memberships and nothing
    else — in particular it never touches an enrollment the group created, which keeps
    its history and only loses ``source_group_id``.
    """

    __tablename__ = "user_group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_user_group_members_pair"),
        Index("ix_user_group_members_user_id", "user_id"),
    )

    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_groups.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    group: Mapped["UserGroup"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship()
