"""Shared, closed schemas for learner-controlled presentation settings."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


class LearningPreferencesV2(BaseModel):
    """Canonical modality contract; interaction is an independent preference."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[2] = 2
    modality: Literal["balanced", "text", "audio", "visual", "data"] = "balanced"
    interaction: Literal["standard", "interactive"] = "standard"
    detail: Literal["concise", "standard", "detailed"] = "standard"
    images: Literal["when_useful", "prefer", "avoid"] = "when_useful"


class LearningPreferencesV3(BaseModel):
    """Web composition and optional delivery modalities are independent axes."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[3] = 3
    web_presentation: Literal["balanced", "text", "visual", "data"] = "balanced"
    modalities: list[Literal["audio", "video"]] = Field(default_factory=list)
    interaction: Literal["standard", "interactive"] = "standard"
    detail: Literal["concise", "standard", "detailed"] = "standard"
    images: Literal["when_useful", "prefer", "avoid"] = "when_useful"


LearningPreferencesSubmit = (
    LearningPreferencesV1 | LearningPreferencesV2 | LearningPreferencesV3
)

__all__ = [
    "AccessibilitySubmit",
    "LearningPreferencesSubmit",
    "LearningPreferencesV1",
    "LearningPreferencesV2",
    "LearningPreferencesV3",
]
