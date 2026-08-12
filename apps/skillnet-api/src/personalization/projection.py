"""Compile live runtime signals into a closed personalization projection.

This boundary deliberately discards free-form role and sector strings. They can still frame
source-grounded examples in the existing runtime, but they are not learner preferences and must
not leak into the shadow planner, its trace, or a shared-cache bucket.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.personalization.plan import (
    AccessibilityCapability,
    ErrorSignal,
    InferredPresentationBucket,
    PersonalizationProjection,
    Presentation,
    SupportBand,
)

CALIBRATION_NODES = 3
_VECTOR_DIMENSIONS = ("texto", "ejercicio", "codigo", "dato")

_EXPERIENCE_SUPPORT = {
    "none": SupportBand.NOVICE,
    "some": SupportBand.GUIDED,
    "experienced": SupportBand.INDEPENDENT,
    "unknown": SupportBand.GUIDED,
}
_SCAFFOLD_SUPPORT = {
    "novice": SupportBand.NOVICE,
    "neutral": SupportBand.GUIDED,
    "advanced": SupportBand.INDEPENDENT,
}
_ERROR_SIGNALS = {
    "detail": ErrorSignal.DETAIL,
    "conceptual": ErrorSignal.CONCEPTUAL,
    "procedural": ErrorSignal.PROCEDURAL,
    "transfer": ErrorSignal.TRANSFER,
}
_VECTOR_BUCKETS = {
    "texto": InferredPresentationBucket.TEXT_HIGH,
    "ejercicio": InferredPresentationBucket.EXERCISE_HIGH,
    "dato": InferredPresentationBucket.DATA_HIGH,
}
_ACCESSIBILITY_CAPABILITIES = {
    "reduce_motion": AccessibilityCapability.REDUCED_MOTION,
    "high_contrast": AccessibilityCapability.HIGH_CONTRAST,
    "extra_time": AccessibilityCapability.EXTRA_TIME,
}
_DECLARED_PRESENTATIONS = {
    "visual": (Presentation.IMAGE, Presentation.DIAGRAM, Presentation.CHART),
    "textual": (Presentation.TEXT, Presentation.TABLE),
    "interactive": (Presentation.SIMULATION,),
}


def _plain(value: Any) -> str:
    if value is None:
        return ""
    return str(getattr(value, "value", value)).strip().lower()


def _density(*, preset: str, base_density: int, accessibility: Mapping[str, Any]) -> int:
    density = max(1, min(3, int(base_density)))
    if preset == "focus" or bool(accessibility.get("short_blocks")):
        density = min(density, 2)
    if preset == "fast":
        density = 1
    return density


def _inferred_bucket(
    format_vector: Mapping[str, Any] | None, *, calibrating: bool
) -> InferredPresentationBucket:
    if calibrating or not format_vector:
        return InferredPresentationBucket.UNKNOWN

    best_dimension = ""
    best_share = 0.0
    for dimension in _VECTOR_DIMENSIONS:
        try:
            share = max(0.0, float(format_vector.get(dimension, 0.0) or 0.0))
        except (TypeError, ValueError):
            share = 0.0
        if share > best_share:
            best_dimension, best_share = dimension, share

    # The legacy vector has no visual dimension. ``codigo`` therefore remains unknown
    # instead of being mislabeled as text or image; VISUAL_HIGH is reserved for evidence
    # that can actually support that claim.
    return _VECTOR_BUCKETS.get(best_dimension, InferredPresentationBucket.UNKNOWN)


def project_runtime_signals(
    *,
    role_title: object | None = None,
    sector: object | None = None,
    experience_level: object | None = "unknown",
    scaffold_band: object | None = None,
    preset: object | None = "standard",
    format_vector: Mapping[str, Any] | None = None,
    accessibility: Mapping[str, Any] | None = None,
    learning_preferences: Mapping[str, Any] | None = None,
    nodes_completed: int = 0,
    last_error_kind: object | None = None,
    base_density: int = 2,
    projection_version: str = "personalization/1",
) -> PersonalizationProjection:
    """Return the deterministic, non-identifying projection used by the planner.

    ``role_title`` and ``sector`` are accepted so callers can pass the existing runtime
    payload without reshaping it, but are intentionally discarded. Raw memory, user IDs and
    event histories are not accepted at all.
    """
    del role_title, sector

    completed = max(0, int(nodes_completed or 0))
    calibrating = completed < CALIBRATION_NODES
    accessibility_values = accessibility or {}
    preference_values = learning_preferences or {}
    declared = _DECLARED_PRESENTATIONS.get(
        _plain(preference_values.get("presentation")), ()
    )
    if _plain(preference_values.get("images")) == "avoid":
        declared = tuple(item for item in declared if item is not Presentation.IMAGE)
    capabilities = frozenset(
        capability
        for key, capability in _ACCESSIBILITY_CAPABILITIES.items()
        if bool(accessibility_values.get(key))
    )

    return PersonalizationProjection(
        declared_presentations=declared,
        inferred_presentation_bucket=_inferred_bucket(
            format_vector, calibrating=calibrating
        ),
        support_band=_SCAFFOLD_SUPPORT.get(
            _plain(scaffold_band),
            _EXPERIENCE_SUPPORT.get(_plain(experience_level), SupportBand.GUIDED),
        ),
        density=_density(
            preset=_plain(preset),
            base_density=base_density,
            accessibility=accessibility_values,
        ),
        accessibility_capabilities=capabilities,
        error_signal=_ERROR_SIGNALS.get(_plain(last_error_kind), ErrorSignal.NONE),
        calibrating=calibrating,
        projection_version=projection_version,
    )
