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


PREFERENCES_VERSION = 3


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


class WebPresentationPreference(str, enum.Enum):
    BALANCED = "balanced"
    TEXT = "text"
    VISUAL = "visual"
    DATA = "data"


class CompanionModality(str, enum.Enum):
    AUDIO = "audio"
    VIDEO = "video"


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
    web_presentation: WebPresentationPreference = WebPresentationPreference.BALANCED
    modalities: tuple[CompanionModality, ...] = ()
    interaction: InteractionPreference = InteractionPreference.STANDARD
    detail: DetailPreference = DetailPreference.STANDARD
    images: ImagePreference = ImagePreference.WHEN_USEFUL

    @property
    def presentation(self) -> PresentationPreference:
        """Legacy projection for runtime code that still consumes v1."""
        if self.interaction is InteractionPreference.INTERACTIVE:
            return PresentationPreference.INTERACTIVE
        return {
            WebPresentationPreference.VISUAL: PresentationPreference.VISUAL,
            WebPresentationPreference.TEXT: PresentationPreference.TEXTUAL,
        }.get(self.web_presentation, PresentationPreference.BALANCED)

    @property
    def modality(self) -> ModalityPreference:
        """Legacy single-value projection for runtime code during v3 rollout."""
        if CompanionModality.AUDIO in self.modalities:
            return ModalityPreference.AUDIO
        return {
            WebPresentationPreference.TEXT: ModalityPreference.TEXT,
            WebPresentationPreference.VISUAL: ModalityPreference.VISUAL,
            WebPresentationPreference.DATA: ModalityPreference.DATA,
        }.get(self.web_presentation, ModalityPreference.BALANCED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "web_presentation": self.web_presentation.value,
            "modalities": [item.value for item in self.modalities],
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
    """Return the canonical v3 bundle, accepting persisted/API v1 and v2 values."""
    if isinstance(value, LearningPreferences):
        return value
    source = value or {}
    raw_version = source.get("version")
    try:
        version = int(raw_version) if raw_version is not None else 1
    except (TypeError, ValueError):
        version = 0
    modalities: tuple[CompanionModality, ...] = ()
    if version == 1:
        legacy = _enum_or_default(
            PresentationPreference,
            source.get("presentation"),
            PresentationPreference.BALANCED,
        )
        web_presentation = {
            PresentationPreference.TEXTUAL: WebPresentationPreference.TEXT,
            PresentationPreference.VISUAL: WebPresentationPreference.VISUAL,
        }.get(legacy, WebPresentationPreference.BALANCED)
        interaction = (
            InteractionPreference.INTERACTIVE
            if legacy is PresentationPreference.INTERACTIVE
            else InteractionPreference.STANDARD
        )
    elif version == 2:
        legacy_modality = _enum_or_default(
            ModalityPreference,
            source.get("modality"),
            ModalityPreference.BALANCED,
        )
        web_presentation = {
            ModalityPreference.TEXT: WebPresentationPreference.TEXT,
            ModalityPreference.VISUAL: WebPresentationPreference.VISUAL,
            ModalityPreference.DATA: WebPresentationPreference.DATA,
        }.get(legacy_modality, WebPresentationPreference.BALANCED)
        if legacy_modality is ModalityPreference.AUDIO:
            modalities = (CompanionModality.AUDIO,)
        interaction = _enum_or_default(
            InteractionPreference,
            source.get("interaction"),
            InteractionPreference.STANDARD,
        )
    elif version == PREFERENCES_VERSION:
        web_presentation = _enum_or_default(
            WebPresentationPreference,
            source.get("web_presentation"),
            WebPresentationPreference.BALANCED,
        )
        raw_modalities = source.get("modalities")
        if isinstance(raw_modalities, (list, tuple)):
            modalities = tuple(
                item
                for item in CompanionModality
                if item.value in {str(value) for value in raw_modalities}
            )
        interaction = _enum_or_default(
            InteractionPreference,
            source.get("interaction"),
            InteractionPreference.STANDARD,
        )
    else:
        return DEFAULT_LEARNING_PREFERENCES
    return LearningPreferences(
        web_presentation=web_presentation,
        modalities=modalities,
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
    """Canonical material for the web-render cache key.

    Companion preferences deliberately do not partition cache entries by themselves. They are
    private resolver signals: the runtime fixes one approved experience and the frontend never
    exposes them as delivery controls.
    ``tts_available`` remains accepted while v2 callers migrate.
    """
    normalized = normalize_learning_preferences(value)
    del tts_available
    return ":".join(
        (
            f"p{normalized.version}",
            normalized.web_presentation.value,
            normalized.interaction.value,
            normalized.detail.value,
            normalized.images.value,
        )
    )
