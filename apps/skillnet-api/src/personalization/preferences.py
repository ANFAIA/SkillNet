"""Closed, versioned learner-declared presentation preferences.

These values may affect shared OpenUI renders, so normalization and cache
serialization live together in this pure module. Raw profile prose never enters this
contract.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


PREFERENCES_VERSION = 1


class PresentationPreference(str, enum.Enum):
    BALANCED = "balanced"
    VISUAL = "visual"
    TEXTUAL = "textual"
    INTERACTIVE = "interactive"


class DetailPreference(str, enum.Enum):
    CONCISE = "concise"
    STANDARD = "standard"
    DETAILED = "detailed"


class ImagePreference(str, enum.Enum):
    WHEN_USEFUL = "when_useful"
    PREFER = "prefer"
    AVOID = "avoid"


@dataclass(frozen=True, slots=True)
class LearningPreferences:
    version: int = PREFERENCES_VERSION
    presentation: PresentationPreference = PresentationPreference.BALANCED
    detail: DetailPreference = DetailPreference.STANDARD
    images: ImagePreference = ImagePreference.WHEN_USEFUL

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "presentation": self.presentation.value,
            "detail": self.detail.value,
            "images": self.images.value,
        }


DEFAULT_LEARNING_PREFERENCES = LearningPreferences()


def _enum_or_default(enum_type, value: object, default):
    plain = getattr(value, "value", value)
    try:
        return enum_type(str(plain))
    except (TypeError, ValueError):
        return default


def normalize_learning_preferences(
    value: Mapping[str, Any] | LearningPreferences | None,
) -> LearningPreferences:
    """Return a valid v1 bundle; unknown/stale storage degrades to neutral defaults."""
    if isinstance(value, LearningPreferences):
        return value
    source = value or {}
    try:
        version = int(source.get("version", PREFERENCES_VERSION))
    except (TypeError, ValueError):
        version = PREFERENCES_VERSION
    if version != PREFERENCES_VERSION:
        return DEFAULT_LEARNING_PREFERENCES
    return LearningPreferences(
        presentation=_enum_or_default(
            PresentationPreference,
            source.get("presentation"),
            PresentationPreference.BALANCED,
        ),
        detail=_enum_or_default(
            DetailPreference, source.get("detail"), DetailPreference.STANDARD
        ),
        images=_enum_or_default(
            ImagePreference, source.get("images"), ImagePreference.WHEN_USEFUL
        ),
    )


def preference_bucket(value: Mapping[str, Any] | LearningPreferences | None) -> str:
    """Canonical, non-identifying material for the shared render cache key."""
    normalized = normalize_learning_preferences(value)
    return ":".join(
        (
            f"p{normalized.version}",
            normalized.presentation.value,
            normalized.detail.value,
            normalized.images.value,
        )
    )
