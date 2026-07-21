"""Skill category model."""

import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, UUIDMixin, TimestampMixin


class SkillCategory(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "skill_categories"
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_skill_categories_org_name"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    skills: Mapped[list["Skill"]] = relationship(back_populates="category")
