"""Shared, closed schemas for learner-controlled presentation settings."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class AccessibilitySubmit(BaseModel):
    """Functional access settings; unknown flags are rejected."""

    model_config = ConfigDict(extra="forbid")

    short_blocks: bool = False
    reduce_motion: bool = False
    high_contrast: bool = False
    extra_time: bool = False


class LearningPreferencesV1(BaseModel):
    """Declared presentation preference; never inferred behaviour or free prose."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    presentation: Literal["balanced", "visual", "textual", "interactive"] = (
        "balanced"
    )
    detail: Literal["concise", "standard", "detailed"] = "standard"
    images: Literal["when_useful", "prefer", "avoid"] = "when_useful"


__all__ = ["AccessibilitySubmit", "LearningPreferencesV1"]
