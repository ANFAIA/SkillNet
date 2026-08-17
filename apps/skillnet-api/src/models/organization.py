"""Organization model."""

import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from src.models.user import User


class WorkspaceMode(str, enum.Enum):
    """How this deployment is used. Fixed per deployment, not inferred from user count.

    ``organization``: companies, teams, classes, academies — an administrator
    manages people who learn. ``individual``: one person who installs SkillNet
    for themselves and both administers and learns. See
    ``docs/design/audience-modes.md``.
    """

    ORGANIZATION = "organization"
    INDIVIDUAL = "individual"


class Organization(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    workspace_mode: Mapped[WorkspaceMode] = mapped_column(
        SAEnum(
            WorkspaceMode,
            name="workspace_mode",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=WorkspaceMode.ORGANIZATION.value,
        default=WorkspaceMode.ORGANIZATION,
    )
    settings: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    users: Mapped[list["User"]] = relationship(back_populates="organization")
