"""User model, extending the fastapi-users base table."""

import enum
import uuid
from datetime import date
from typing import TYPE_CHECKING

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from sqlalchemy import Date, Enum as SAEnum, ForeignKey, String, UniqueConstraint, text
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
    __table_args__ = (UniqueConstraint("org_id", "email", name="uq_users_org_email"),)

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

    organization: Mapped["Organization"] = relationship(back_populates="users")
