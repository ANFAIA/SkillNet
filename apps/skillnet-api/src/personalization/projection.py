"""Compile live runtime signals into a closed personalization projection.

This boundary deliberately discards free-form role and sector strings. They can still frame
source-grounded examples in the existing runtime, but they are not learner preferences and must
not leak into the shadow planner, its trace, or a shared-cache bucket.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.personalization.plan import (
    AccessibilityCapability,
    ErrorSignal,
    HistorySupportLevel,
    InferredPresentationBucket,
    PersonalizationProjection,
    Presentation,
    SupportBand,
)
from src.personalization.modality import resolve_declared_modality, tts_is_available
from src.personalization.preferences import (
    InteractionPreference,
    ModalityPreference,
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
    ModalityPreference.TEXT: (Presentation.TEXT,),
    ModalityPreference.AUDIO: (Presentation.AUDIO,),
    ModalityPreference.VISUAL: (
        Presentation.IMAGE,
        Presentation.DIAGRAM,
        Presentation.CHART,
    ),
    ModalityPreference.DATA: (Presentation.TABLE, Presentation.CHART),
}


@dataclass(frozen=True, slots=True)
class ValidatedHistoryEvent:
    """Minimal EventPort row accepted by the longitudinal projector."""

    event_id: str
    type: str
    component_id: str
    attempt_id: str | None = None
    outcome: str | None = None
    score: float | None = None


@dataclass(frozen=True, slots=True)
class LongitudinalHistoryProjection:
    """Closed decision input; no identity, timestamps, answers, or free text."""

    evaluated_attempts: int = 0
    error_attempts: int = 0
    supported_error_attempts: int = 0
    mechanic_exposure: tuple[tuple[str, int], ...] = ()
    support_level: HistorySupportLevel = HistorySupportLevel.BASE
    applied: bool = False
    evidence_policy: str = "eventport-evaluated/1"
    semantic_error_mapping: str = "shadow-unmapped"

    @property
    def decision_digest(self) -> str:
        """Digest only fields that can change the next render decision."""

        material = {
            "applied": self.applied,
            "mechanic_exposure": self.mechanic_exposure if self.applied else (),
            "support_level": (
                self.support_level.value
                if self.applied
                else HistorySupportLevel.BASE.value
            ),
            "version": self.evidence_policy,
        }
        encoded = json.dumps(
            material, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        )
        return "ld1:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def longitudinal_projection_from_mapping(
    value: Mapping[str, Any] | None,
) -> LongitudinalHistoryProjection:
    """Rehydrate the closed graph-state projection, failing back to no evidence."""

    source = value or {}
    raw_exposure = source.get("mechanic_exposure")
    exposure: list[tuple[str, int]] = []
    if isinstance(raw_exposure, (list, tuple)):
        for item in raw_exposure:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            component_id, count = item
            if isinstance(component_id, str) and component_id.startswith("didact."):
                exposure.append((component_id, min(2, max(1, int(count)))))
    try:
        support = HistorySupportLevel(str(source.get("support_level") or "base"))
    except ValueError:
        support = HistorySupportLevel.BASE
    return LongitudinalHistoryProjection(
        evaluated_attempts=max(0, int(source.get("evaluated_attempts") or 0)),
        error_attempts=max(0, int(source.get("error_attempts") or 0)),
        supported_error_attempts=max(
            0, int(source.get("supported_error_attempts") or 0)
        ),
        mechanic_exposure=tuple(sorted(set(exposure))),
        support_level=support,
        applied=bool(source.get("applied")),
        evidence_policy=(
            str(source.get("evidence_policy"))
            if str(source.get("evidence_policy") or "").strip()
            else "eventport-evaluated/1"
        ),
        semantic_error_mapping="shadow-unmapped",
    )


def project_longitudinal_history(
    events: tuple[ValidatedHistoryEvent, ...] | list[ValidatedHistoryEvent],
    *,
    nodes_completed: int,
) -> LongitudinalHistoryProjection:
    """Compile prior scored Didact responses into bounded next-node signals.

    Exposure, attempts, completion and unscored responses are deliberately inert.
    Feedback affects support only when its ``attempt_id`` matches a validated scored
    error. Counts are bucketed at two to avoid fragmenting the shared cache per click.
    """

    evaluated: dict[str, ValidatedHistoryEvent] = {}
    feedback_attempts: set[str] = set()
    for event in events:
        if not event.component_id.startswith("didact."):
            continue
        if event.type == "didact.feedback_viewed" and event.attempt_id:
            feedback_attempts.add(event.attempt_id)
            continue
        if event.type != "didact.answered":
            continue
        if event.outcome not in {"correct", "incorrect", "partial"}:
            continue
        if event.score is None or not 0.0 <= event.score <= 1.0:
            continue
        attempt_key = event.attempt_id or event.event_id
        evaluated.setdefault(attempt_key, event)

    errors = {
        attempt_id
        for attempt_id, event in evaluated.items()
        if event.outcome in {"incorrect", "partial"}
    }
    mechanics = Counter(event.component_id for event in evaluated.values())
    mechanic_exposure = tuple(
        (component_id, min(2, count))
        for component_id, count in sorted(mechanics.items())
    )
    error_count = len(errors)
    supported_error_count = len(errors & feedback_attempts)
    if error_count >= 2 or supported_error_count >= 1:
        support = HistorySupportLevel.WORKED_EXAMPLE
    elif error_count == 1:
        support = HistorySupportLevel.HINTS
    else:
        support = HistorySupportLevel.BASE
    applied = max(0, int(nodes_completed or 0)) >= CALIBRATION_NODES
    return LongitudinalHistoryProjection(
        evaluated_attempts=len(evaluated),
        error_attempts=error_count,
        supported_error_attempts=supported_error_count,
        mechanic_exposure=mechanic_exposure,
        support_level=support if applied else HistorySupportLevel.BASE,
        applied=applied,
    )


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
    tts_available: bool | None = None,
    longitudinal_history: LongitudinalHistoryProjection | None = None,
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
    if tts_available is None:
        from src.config import settings

        resolved_tts_available = tts_is_available(settings.TTS_PROVIDER)
    else:
        resolved_tts_available = tts_available
    modality = resolve_declared_modality(
        preference_values,
        tts_available=resolved_tts_available,
    )
    declared = _DECLARED_PRESENTATIONS.get(modality.effective, ())
    if modality.interaction is InteractionPreference.INTERACTIVE:
        declared = (*declared, Presentation.SIMULATION)
    if _plain(preference_values.get("images")) == "avoid":
        declared = tuple(item for item in declared if item is not Presentation.IMAGE)
    capabilities = frozenset(
        capability
        for key, capability in _ACCESSIBILITY_CAPABILITIES.items()
        if bool(accessibility_values.get(key))
    )
    history = longitudinal_history or LongitudinalHistoryProjection()
    history_applied = bool(history.applied and not calibrating)

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
        history_support_level=(
            history.support_level if history_applied else HistorySupportLevel.BASE
        ),
        mechanic_exposure=history.mechanic_exposure if history_applied else (),
        history_evidence_applied=history_applied,
        semantic_error_mapping=history.semantic_error_mapping,
        calibrating=calibrating,
        projection_version=projection_version,
    )
