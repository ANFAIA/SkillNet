"""Resolve declared learning modality against deployment capabilities.

This boundary selects presentation only. It never rewrites a node objective,
mission, source function, or assessment intent.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from src.core.logging import get_logger
from src.personalization.preferences import (
    InteractionPreference,
    ModalityPreference,
    normalize_learning_preferences,
)

FallbackReason = Literal["tts_disabled"]
logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ModalityResolution:
    requested: ModalityPreference
    effective: ModalityPreference
    interaction: InteractionPreference
    fallback_reason: FallbackReason | None = None

    def trace(self) -> dict[str, str | None]:
        return {
            "requested_modality": self.requested.value,
            "effective_modality": self.effective.value,
            "interaction": self.interaction.value,
            "fallback_reason": self.fallback_reason,
        }


def tts_is_available(provider: object | None) -> bool:
    return str(provider or "").strip().lower() not in {"", "disabled"}


def resolve_declared_modality(
    value: Mapping[str, Any] | None,
    *,
    tts_available: bool,
) -> ModalityResolution:
    preferences = normalize_learning_preferences(value)
    requested = preferences.modality
    if requested is ModalityPreference.AUDIO and not tts_available:
        resolution = ModalityResolution(
            requested=requested,
            effective=ModalityPreference.TEXT,
            interaction=preferences.interaction,
            fallback_reason="tts_disabled",
        )
        logger.info(
            "Declared audio modality degraded to text",
            extra={"modality_trace": resolution.trace()},
        )
        return resolution
    return ModalityResolution(
        requested=requested,
        effective=requested,
        interaction=preferences.interaction,
    )
