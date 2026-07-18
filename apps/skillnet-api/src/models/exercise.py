"""Exercise model."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum, ForeignKey, Integer, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, UUIDMixin

if TYPE_CHECKING:
    from src.models.exercise_attempt import ExerciseAttempt
    from src.models.lesson import Lesson


class ExerciseType(str, enum.Enum):
    TEST = "test"
    TRUE_FALSE = "true_false"
    FILL_BLANK = "fill_blank"
    ORDER_STEPS = "order_steps"
    PRACTICAL_CASE = "practical_case"
    DIALOGUE = "dialogue"


class Exercise(UUIDMixin, Base):
    __tablename__ = "exercises"

    lesson_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[ExerciseType] = mapped_column(
        SAEnum(
            ExerciseType,
            name="exercise_type",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    lesson: Mapped["Lesson"] = relationship(back_populates="exercises")
    attempts: Mapped[list["ExerciseAttempt"]] = relationship(back_populates="exercise")
