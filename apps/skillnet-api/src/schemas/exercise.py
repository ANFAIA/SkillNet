"""Exercise + attempt schemas, shared by course viewing and Phase 4 generation."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

# Keys whose presence would reveal the answer to an employee taking an exercise.
_ANSWER_KEYS = (
    "correct",
    "correct_order",
    "blanks",
    "rubric",
    "evaluation_criteria",
    "system_prompt",
)


def strip_answers(content: dict, exercise_type: str) -> dict:
    """Return a copy of ``content`` with answer-revealing keys removed."""
    return {k: v for k, v in content.items() if k not in _ANSWER_KEYS}


class ExerciseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    content: dict
    position: int


class AttemptRequest(BaseModel):
    # Raw per-type body (see backend-api.md 4.2); the grader validates its shape.
    answer: Any


class AttemptResult(BaseModel):
    score: float
    passed: bool
    feedback: str | None = None
    explanation: str | None = None


class AttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    exercise_id: uuid.UUID
    score: float
    passed: bool
    feedback: str | None = None
    attempted_at: datetime
