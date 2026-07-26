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

from src.services.learner_profile_service import is_calibrating

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
    experience_level: Experience = "unknown"
    preset: Preset = "standard"
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
            experience_level=_plain(profile.experience_level),
            preset=_plain(profile.preset),
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


def _plain(value: object) -> str:
    return str(getattr(value, "value", value))
