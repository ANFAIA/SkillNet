"""Deterministic, framework-independent learning-experience planning.

This is a shadow planner: callers can compare its decision with the live pipeline, but
it deliberately has no integration with LangGraph or rendering.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class CognitiveMission(str, enum.Enum):
    RECOGNIZE = "recognize"
    RECONSTRUCT = "reconstruct"
    INTERPRET = "interpret"
    DECIDE = "decide"
    EXPLAIN = "explain"
    PRODUCE = "produce"


class Presentation(str, enum.Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    TABLE = "table"
    CHART = "chart"
    DIAGRAM = "diagram"
    SIMULATION = "simulation"


class SourceFunction(str, enum.Enum):
    ENUMERATE = "enumerate"
    PROCEDURE = "procedure"
    QUANTIFY = "quantify"
    CONTRAST = "contrast"
    VARY = "vary"
    EXPLORE = "explore"
    LOCATE = "locate"
    ASSESS = "assess"


class SupportBand(str, enum.Enum):
    NOVICE = "novice"
    GUIDED = "guided"
    INDEPENDENT = "independent"


class AccessibilityCapability(str, enum.Enum):
    KEYBOARD = "keyboard"
    SCREEN_READER = "screen_reader"
    REDUCED_MOTION = "reduced_motion"
    HIGH_CONTRAST = "high_contrast"
    EXTRA_TIME = "extra_time"
    NO_DRAG_ALTERNATIVE = "no_drag_alternative"


class InferredPresentationBucket(str, enum.Enum):
    UNKNOWN = "unknown"
    TEXT_HIGH = "text-high"
    VISUAL_HIGH = "visual-high"
    EXERCISE_HIGH = "exercise-high"
    DATA_HIGH = "data-high"


_PRESENTATIONS_FOR_INFERRED_BUCKET: dict[
    InferredPresentationBucket, frozenset[Presentation]
] = {
    InferredPresentationBucket.TEXT_HIGH: frozenset(
        {Presentation.TEXT, Presentation.TABLE}
    ),
    InferredPresentationBucket.VISUAL_HIGH: frozenset(
        {Presentation.IMAGE, Presentation.DIAGRAM}
    ),
    InferredPresentationBucket.EXERCISE_HIGH: frozenset({Presentation.SIMULATION}),
    InferredPresentationBucket.DATA_HIGH: frozenset(
        {Presentation.CHART, Presentation.TABLE}
    ),
}


class ErrorSignal(str, enum.Enum):
    NONE = "none"
    DETAIL = "detail"
    CONCEPTUAL = "conceptual"
    PROCEDURAL = "procedural"
    TRANSFER = "transfer"


class HistorySupportLevel(str, enum.Enum):
    """Bounded support inferred only from validated prior assessment evidence."""

    BASE = "base"
    HINTS = "hints"
    WORKED_EXAMPLE = "worked-example"


class ProducerKind(str, enum.Enum):
    """Producer contract; deliberately separate from the learner's mission."""

    CONTENT = "content"
    ASSESSMENT = "assessment"
    MEDIA = "media"
    SIMULATION = "simulation"
    DETERMINISTIC = "deterministic"


@dataclass(frozen=True, slots=True)
class LearningObjective:
    """Stable learning intent and source-backed constraints for one node."""

    objective_id: str
    objective_version: int
    mission: CognitiveMission
    source_functions: frozenset[SourceFunction]
    available_requirements: frozenset[str] = frozenset()
    required_fact_refs: tuple[str, ...] = ()
    required_safety_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.objective_id.strip():
            raise ValueError("objective_id must not be empty")
        if self.objective_version < 1:
            raise ValueError("objective_version must be positive")
        if not self.source_functions:
            raise ValueError("at least one source function is required")


@dataclass(frozen=True, slots=True)
class PersonalizationProjection:
    """Closed, non-identifying projection; never raw profile text or events."""

    declared_presentations: tuple[Presentation, ...] = ()
    inferred_presentation_bucket: InferredPresentationBucket = (
        InferredPresentationBucket.UNKNOWN
    )
    support_band: SupportBand = SupportBand.GUIDED
    density: int = 2
    accessibility_capabilities: frozenset[AccessibilityCapability] = frozenset()
    error_signal: ErrorSignal = ErrorSignal.NONE
    history_support_level: HistorySupportLevel = HistorySupportLevel.BASE
    mechanic_exposure: tuple[tuple[str, int], ...] = ()
    history_evidence_applied: bool = False
    semantic_error_mapping: str = "shadow-unmapped"
    calibrating: bool = False
    projection_version: str = "personalization/1"

    def __post_init__(self) -> None:
        if not 1 <= self.density <= 3:
            raise ValueError("density must be between 1 and 3")
        if not self.projection_version.strip():
            raise ValueError("projection_version must not be empty")
        if len(set(self.declared_presentations)) != len(self.declared_presentations):
            raise ValueError("declared_presentations must not contain duplicates")
        if any(not component_id.startswith("didact.") for component_id, _ in self.mechanic_exposure):
            raise ValueError("mechanic_exposure accepts only Didact component ids")
        if any(count not in (1, 2) for _, count in self.mechanic_exposure):
            raise ValueError("mechanic exposure counts must be bucketed to 1 or 2")


@dataclass(frozen=True, slots=True)
class SupportPolicy:
    band: SupportBand
    density: int
    worked_example: bool
    graduated_hints: bool
    direct_feedback: bool
    history_level: HistorySupportLevel = HistorySupportLevel.BASE


@dataclass(frozen=True, slots=True)
class ComponentDescriptor:
    """Pedagogical capabilities exported by any component catalogue."""

    component_id: str
    version: int
    missions: frozenset[CognitiveMission]
    source_functions: frozenset[SourceFunction]
    presentations: frozenset[Presentation]
    producer_kind: ProducerKind = ProducerKind.DETERMINISTIC
    affordances: frozenset[str] = frozenset()
    evidence_events: frozenset[str] = frozenset()
    state_model_ref: str | None = None
    requirements: frozenset[str] = frozenset()
    accessibility: frozenset[AccessibilityCapability] = frozenset()
    rank: int = 100

    def __post_init__(self) -> None:
        if not self.component_id.strip():
            raise ValueError("component_id must not be empty")
        if self.version < 1:
            raise ValueError("component version must be positive")
        if not self.missions or not self.source_functions or not self.presentations:
            raise ValueError("component capabilities must not be empty")


@dataclass(frozen=True, slots=True)
class ComponentCandidate:
    component_id: str
    version: int
    presentation: Presentation
    producer_kind: ProducerKind
    affordances: frozenset[str]
    evidence_events: frozenset[str]
    state_model_ref: str | None
    rank: int


class DeclineReason(str, enum.Enum):
    EMPTY_CATALOG = "empty_catalog"
    MISSION_UNSUPPORTED = "mission_unsupported"
    SOURCE_UNSUPPORTED = "source_unsupported"
    MISSING_REQUIREMENTS = "missing_requirements"
    ACCESSIBILITY_UNSUPPORTED = "accessibility_unsupported"


@dataclass(frozen=True, slots=True)
class Decline:
    reason: DeclineReason
    component_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Declined:
    reasons: tuple[Decline, ...]


@dataclass(frozen=True, slots=True)
class LearningExperiencePlan:
    objective_id: str
    objective_version: int
    mission: CognitiveMission
    source_functions: tuple[SourceFunction, ...]
    representations: tuple[Presentation, ...]
    required_fact_refs: tuple[str, ...]
    required_safety_refs: tuple[str, ...]
    support: SupportPolicy
    component_candidates: tuple[ComponentCandidate, ...]
    rationale_codes: tuple[str, ...]
    policy_version: str
    projection_version: str


def _support_for(projection: PersonalizationProjection) -> SupportPolicy:
    needs_guidance = projection.support_band is not SupportBand.INDEPENDENT
    history_hints = projection.history_support_level in (
        HistorySupportLevel.HINTS,
        HistorySupportLevel.WORKED_EXAMPLE,
    )
    return SupportPolicy(
        band=projection.support_band,
        density=projection.density,
        worked_example=(
            projection.support_band is SupportBand.NOVICE
            or projection.history_support_level is HistorySupportLevel.WORKED_EXAMPLE
        ),
        graduated_hints=(
            needs_guidance
            or projection.error_signal is not ErrorSignal.NONE
            or history_hints
        ),
        direct_feedback=True,
        history_level=projection.history_support_level,
    )


def _decline_reasons(
    objective: LearningObjective,
    projection: PersonalizationProjection,
    catalog: tuple[ComponentDescriptor, ...],
) -> tuple[Decline, ...]:
    if not catalog:
        return (Decline(DeclineReason.EMPTY_CATALOG),)

    checks = (
        (DeclineReason.MISSION_UNSUPPORTED, lambda item: objective.mission in item.missions),
        (
            DeclineReason.SOURCE_UNSUPPORTED,
            lambda item: bool(objective.source_functions & item.source_functions),
        ),
        (
            DeclineReason.MISSING_REQUIREMENTS,
            lambda item: item.requirements <= objective.available_requirements,
        ),
        (
            DeclineReason.ACCESSIBILITY_UNSUPPORTED,
            lambda item: projection.accessibility_capabilities <= item.accessibility,
        ),
    )
    remaining = catalog
    declines: list[Decline] = []
    for reason, predicate in checks:
        rejected = tuple(item.component_id for item in remaining if not predicate(item))
        if rejected:
            declines.append(Decline(reason, rejected))
        remaining = tuple(item for item in remaining if predicate(item))
    return tuple(declines)


def plan_experience(
    objective: LearningObjective,
    projection: PersonalizationProjection,
    catalog: tuple[ComponentDescriptor, ...],
    *,
    policy_version: str = "learning-experience/1",
) -> LearningExperiencePlan | Declined:
    """Resolve an objective against capabilities, without side effects.

    Declared presentations are preferred when available. If unavailable, a valid
    fallback remains eligible and the plan records that fact honestly.
    """
    if not policy_version.strip():
        raise ValueError("policy_version must not be empty")

    eligible = tuple(
        item
        for item in catalog
        if objective.mission in item.missions
        and bool(objective.source_functions & item.source_functions)
        and item.requirements <= objective.available_requirements
        and projection.accessibility_capabilities <= item.accessibility
    )
    if not eligible:
        return Declined(_decline_reasons(objective, projection, catalog))

    declared = projection.declared_presentations
    preferred = tuple(
        item for item in eligible if any(value in item.presentations for value in declared)
    )
    pool = preferred or eligible
    fallback = bool(declared and not preferred)

    inferred_presentations = (
        frozenset()
        if projection.calibrating
        else _PRESENTATIONS_FOR_INFERRED_BUCKET.get(
            projection.inferred_presentation_bucket, frozenset()
        )
    )

    def presentation_for(item: ComponentDescriptor) -> Presentation:
        for value in declared:
            if value in item.presentations:
                return value
        for value in sorted(inferred_presentations, key=lambda value: value.value):
            if value in item.presentations:
                return value
        return min(item.presentations, key=lambda value: value.value)

    def candidate_rank(item: ComponentDescriptor) -> tuple[int, int, str, int]:
        # Behaviour learned during calibration is a secondary, deterministic signal.
        # It never makes an ineligible component eligible and cannot escape the pool
        # already narrowed by an explicit declared presentation.
        inferred_penalty = int(
            bool(inferred_presentations)
            and not bool(item.presentations & inferred_presentations)
        )
        return (item.rank, inferred_penalty, item.component_id, item.version)

    candidates = tuple(
        ComponentCandidate(
            item.component_id,
            item.version,
            presentation_for(item),
            item.producer_kind,
            item.affordances,
            item.evidence_events,
            item.state_model_ref,
            item.rank,
        )
        for item in sorted(pool, key=candidate_rank)
    )
    if projection.history_evidence_applied and projection.mechanic_exposure:
        from src.personalization.novelty import useful_novelty_tiebreak

        candidates_before_novelty = candidates
        candidates = useful_novelty_tiebreak(
            candidates,
            prior_exposure=dict(projection.mechanic_exposure),
        )
    else:
        candidates_before_novelty = candidates
    representations = tuple(dict.fromkeys(item.presentation for item in candidates))
    rationale = ["MISSION_FROM_OBJECTIVE", "CAPABILITY_FILTERED"]
    if declared and preferred:
        rationale.append("DECLARED_PRESENTATION_MATCHED")
    elif fallback:
        rationale.append("DECLARED_PRESENTATION_UNAVAILABLE")
    if projection.accessibility_capabilities:
        rationale.append("ACCESSIBILITY_FILTERED")
    if inferred_presentations and any(
        item.presentations & inferred_presentations for item in pool
    ):
        rationale.append("INFERRED_PRESENTATION_RANKED")
    if projection.history_support_level is not HistorySupportLevel.BASE:
        rationale.append("VALIDATED_HISTORY_SUPPORT_ESCALATED")
    if candidates != candidates_before_novelty:
        rationale.append("USEFUL_NOVELTY_TIEBREAK")

    return LearningExperiencePlan(
        objective_id=objective.objective_id,
        objective_version=objective.objective_version,
        mission=objective.mission,
        source_functions=tuple(sorted(objective.source_functions, key=lambda item: item.value)),
        representations=representations,
        required_fact_refs=objective.required_fact_refs,
        required_safety_refs=objective.required_safety_refs,
        support=_support_for(projection),
        component_candidates=candidates,
        rationale_codes=tuple(rationale),
        policy_version=policy_version,
        projection_version=projection.projection_version,
    )
