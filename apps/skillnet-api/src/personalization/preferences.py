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


PREFERENCES_VERSION = 2


class PresentationPreference(str, enum.Enum):
    BALANCED = "balanced"
    VISUAL = "visual"
    TEXTUAL = "textual"
    INTERACTIVE = "interactive"


class ModalityPreference(str, enum.Enum):
    BALANCED = "balanced"
    TEXT = "text"
    AUDIO = "audio"
    VISUAL = "visual"
    DATA = "data"


class InteractionPreference(str, enum.Enum):
    STANDARD = "standard"
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
    modality: ModalityPreference = ModalityPreference.BALANCED
    interaction: InteractionPreference = InteractionPreference.STANDARD
    detail: DetailPreference = DetailPreference.STANDARD
    images: ImagePreference = ImagePreference.WHEN_USEFUL

    @property
    def presentation(self) -> PresentationPreference:
        """Legacy projection for runtime code that still consumes v1."""
        if self.interaction is InteractionPreference.INTERACTIVE:
            return PresentationPreference.INTERACTIVE
        return {
            ModalityPreference.VISUAL: PresentationPreference.VISUAL,
            ModalityPreference.TEXT: PresentationPreference.TEXTUAL,
        }.get(self.modality, PresentationPreference.BALANCED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "modality": self.modality.value,
            "interaction": self.interaction.value,
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
    """Return the canonical v2 bundle, accepting persisted/API v1 values."""
    if isinstance(value, LearningPreferences):
        return value
    source = value or {}
    raw_version = source.get("version")
    try:
        version = int(raw_version) if raw_version is not None else 1
    except (TypeError, ValueError):
        version = 0
    if version == 1:
        legacy = _enum_or_default(
            PresentationPreference,
            source.get("presentation"),
            PresentationPreference.BALANCED,
        )
        modality = {
            PresentationPreference.TEXTUAL: ModalityPreference.TEXT,
            PresentationPreference.VISUAL: ModalityPreference.VISUAL,
        }.get(legacy, ModalityPreference.BALANCED)
        interaction = (
            InteractionPreference.INTERACTIVE
            if legacy is PresentationPreference.INTERACTIVE
            else InteractionPreference.STANDARD
        )
    elif version == PREFERENCES_VERSION:
        modality = _enum_or_default(
            ModalityPreference,
            source.get("modality"),
            ModalityPreference.BALANCED,
        )
        interaction = _enum_or_default(
            InteractionPreference,
            source.get("interaction"),
            InteractionPreference.STANDARD,
        )
    else:
        return DEFAULT_LEARNING_PREFERENCES
    return LearningPreferences(
        modality=modality,
        interaction=interaction,
        detail=_enum_or_default(
            DetailPreference, source.get("detail"), DetailPreference.STANDARD
        ),
        images=_enum_or_default(
            ImagePreference, source.get("images"), ImagePreference.WHEN_USEFUL
        ),
    )


def preference_bucket(
    value: Mapping[str, Any] | LearningPreferences | None,
    *,
    tts_available: bool | None = None,
) -> str:
    """Canonical, non-identifying material for the shared render cache key.

    A deployment without TTS keys declared audio as its effective text modality,
    so both requests can safely share the same text render.
    """
    normalized = normalize_learning_preferences(value)
    modality = normalized.modality
    if tts_available is False and modality is ModalityPreference.AUDIO:
        modality = ModalityPreference.TEXT
    return ":".join(
        (
            f"p{normalized.version}",
            modality.value,
            normalized.interaction.value,
            normalized.detail.value,
            normalized.images.value,
        )
    )
