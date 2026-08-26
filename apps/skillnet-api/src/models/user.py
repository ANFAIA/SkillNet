"""User model, extending the fastapi-users base table."""

import enum
import uuid
from datetime import date
from typing import TYPE_CHECKING

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from sqlalchemy import (
    Date,
    Enum as SAEnum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.organization import Organization


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    EMPLOYEE = "employee"


class LearningProfile(str, enum.Enum):
    STANDARD = "standard"
    FOCUS = "focus"
    FAST = "fast"


class User(SQLAlchemyBaseUserTableUUID, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("org_id", "email", name="uq_users_org_email"),
        Index(
            "uq_users_google_sub",
            "google_sub",
            unique=True,
            postgresql_where=text("google_sub IS NOT NULL"),
        ),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(
            UserRole,
            name="user_role",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=UserRole.EMPLOYEE,
    )
    learning_profile: Mapped[LearningProfile] = mapped_column(
        SAEnum(
            LearningProfile,
            name="learning_profile",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=LearningProfile.STANDARD,
    )
    accessibility: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    hired_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: Google's stable subject identifier (the OIDC ``sub`` claim) for this account,
    #: set the first time the person signs in with Google. The email is deliberately
    #: NOT the identity key: a Google address can be reassigned inside a Workspace
    #: domain, and a person can change theirs, while ``sub`` never changes and is
    #: never reused. Unique across the whole table rather than per organization —
    #: one external identity resolves to exactly one account, with no org context
    #: available at the moment of the lookup. Null for password-only accounts.
    google_sub: Mapped[str | None] = mapped_column(String, nullable=True)

    organization: Mapped["Organization"] = relationship(back_populates="users")
