"""Learner-profile schemas (§11.2).

``format_vector`` and ``tutor_notes`` are **never** exposed to the client. They are
inference state, not a user-facing setting, and shipping them would invite a
frontend to start branching on them. ``calibrating`` is the one derived bit the
client legitimately needs.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.learning_preferences import (
    AccessibilitySubmit,
    LearningPreferencesSubmit,
    LearningPreferencesV3,
)
from src.services.learner_profile_service import is_calibrating
from src.personalization.learning_note import LEARNING_NOTE_MAX_CHARS
from src.personalization.preferences import normalize_learning_preferences

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps this module DB-unaware
    from src.models import LearnerProfile

Experience = str
Preset = str


class LearnerProfileRead(BaseModel):
    """What the employee sees about their own profile."""

    model_config = ConfigDict(from_attributes=True)

    role_title: str | None = None
    sector: str | None = None
    goal: str | None = None
    learning_note: str | None = None
    experience_level: Experience = "unknown"
    preset: Preset = "standard"
    learning_preferences: LearningPreferencesV3 = Field(
        default_factory=LearningPreferencesV3
    )
    nodes_completed: int = 0
    onboarding_completed_at: datetime | None = None
    onboarding_skipped: bool = False
    calibrating: bool = True

    @classmethod
    def from_profile(cls, profile: LearnerProfile) -> LearnerProfileRead:
        return cls(
            role_title=profile.role_title,
            sector=profile.sector,
            goal=profile.goal,
            learning_note=getattr(profile, "learning_note", None),
            experience_level=_plain(profile.experience_level),
            preset=_plain(profile.preset),
            learning_preferences=LearningPreferencesV3.model_validate(
                normalize_learning_preferences(
                    getattr(profile, "learning_preferences", None)
                ).to_dict()
            ),
            nodes_completed=profile.nodes_completed,
            onboarding_completed_at=profile.onboarding_completed_at,
            onboarding_skipped=profile.onboarding_skipped,
            calibrating=is_calibrating(profile.nodes_completed),
        )


class LearnerProfileUpdate(BaseModel):
    """``PATCH`` body: only the four fields §11.2 declares editable.

    ``experience_level`` is **not** here on purpose. Re-declaring experience moves
    ``scaffold_band`` for every course at once; redoing the onboarding is the
    supported path.
    """

    model_config = ConfigDict(extra="forbid")

    preset: str | None = Field(default=None, pattern="^(standard|focus|fast)$")
    role_title: str | None = Field(default=None, max_length=120)
    sector: str | None = Field(default=None, max_length=120)
    goal: str | None = Field(default=None, max_length=200)
    # The learner's own "how I like to learn" note. Free text, length-capped: it steers only
    # HOW a lesson is explained and is treated as data (never as instructions) downstream.
    learning_note: str | None = Field(default=None, max_length=LEARNING_NOTE_MAX_CHARS)
    learning_preferences: LearningPreferencesSubmit | None = None
    accessibility: AccessibilitySubmit | None = None


class LearnerMemoryRead(BaseModel):
    """The narrative memory the learner may read: the notebook markdown and its timestamp.

    Unlike ``format_vector``/``tutor_notes``, this field IS exposed — it is the learner's own
    prose memory, and the whole point is that they can see and edit it (GDPR access). The
    admin has no route to it.
    """

    memory_md: str
    memory_updated_at: datetime | None = None


class LearnerMemoryUpdate(BaseModel):
    """``PUT`` body: the learner's edited notebook (GDPR rectification).

    Stored normalized back to the five canonical sections and size-capped by
    :func:`src.services.learner_memory.normalize_for_storage`.
    """

    model_config = ConfigDict(extra="forbid")

    memory_md: str = Field(max_length=20_000)


def _plain(value: object) -> str:
    return str(getattr(value, "value", value))
