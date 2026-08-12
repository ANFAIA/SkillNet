"""Pure evaluation for component-selection experiments.

This module deliberately knows nothing about React component names, the live runtime, an
LLM provider or a particular catalogue.  It evaluates the *capabilities delivered* by a
selection strategy against a scenario declared before the run.

Safety and validity are gates, not points: a visually rich result cannot compensate for
a lost critical fact or an inaccessible interaction.  Efficiency is carried beside the
quality result and never contributes to its score.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any


class ExpectedOutcome(str, enum.Enum):
    PRODUCE = "produce"
    DECLINE = "decline"
    EITHER = "either"


class GateCode(str, enum.Enum):
    OUTCOME_MISMATCH = "outcome_mismatch"
    INVALID_SPEC = "invalid_spec"
    UNREACHABLE_CONTENT = "unreachable_content"
    CRITICAL_FACT_MISSING = "critical_fact_missing"
    CRITICAL_FACT_CONTRADICTED = "critical_fact_contradicted"
    UNSUPPORTED_CRITICAL_CLAIM = "unsupported_critical_claim"
    EVALUATION_UNGROUNDED = "evaluation_ungrounded"
    ACCESSIBILITY_REQUIRED_MISSING = "accessibility_required_missing"


@dataclass(frozen=True, slots=True)
class WeightedRequirement:
    id: str
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("requirement id must not be empty")
        if self.weight <= 0:
            raise ValueError("requirement weight must be positive")


@dataclass(frozen=True, slots=True)
class SelectionExpectations:
    """Gold requirements for one objective/profile cell.

    Required accessibility is a gate.  Desired accessibility is useful-but-optional
    coverage (for example reduced motion when it is not mandatory for this learner).
    Preferences only list effects applicable to this content; an irrelevant preference
    must not create free points or force decorative variation.
    """

    scenario_id: str
    expected_outcome: ExpectedOutcome = ExpectedOutcome.PRODUCE
    critical_facts: tuple[WeightedRequirement, ...] = ()
    required_affordances: tuple[WeightedRequirement, ...] = ()
    required_evidence: tuple[WeightedRequirement, ...] = ()
    applicable_preferences: tuple[WeightedRequirement, ...] = ()
    required_accessibility: tuple[WeightedRequirement, ...] = ()
    desired_accessibility: tuple[WeightedRequirement, ...] = ()
    target_depth: int = 0

    def __post_init__(self) -> None:
        if not self.scenario_id.strip():
            raise ValueError("scenario_id must not be empty")
        if not 0 <= self.target_depth <= 4:
            raise ValueError("target_depth must be between 0 and 4")
        for field_name in (
            "critical_facts",
            "required_affordances",
            "required_evidence",
            "applicable_preferences",
            "required_accessibility",
            "desired_accessibility",
        ):
            values = getattr(self, field_name)
            ids = [item.id for item in values]
            if len(ids) != len(set(ids)):
                raise ValueError(f"{field_name} must not contain duplicate ids")


@dataclass(frozen=True, slots=True)
class EfficiencyMetrics:
    """Operational measurements, intentionally excluded from pedagogical quality."""

    latency_ms: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    attempts: int | None = None

    def __post_init__(self) -> None:
        for field_name in ("latency_ms", "tokens_in", "tokens_out", "attempts"):
            value = getattr(self, field_name)
            if value is not None and value < 0:
                raise ValueError(f"{field_name} must not be negative")
        if self.cost_usd is not None and self.cost_usd < 0:
            raise ValueError("cost_usd must not be negative")


@dataclass(frozen=True, slots=True)
class SelectionObservation:
    """Capabilities and invariants observed in the final, reachable experience."""

    declined: bool = False
    decline_reason: str | None = None
    valid_spec: bool = True
    fully_reachable: bool = True
    evaluation_grounded: bool = True
    facts_covered: frozenset[str] = frozenset()
    facts_contradicted: frozenset[str] = frozenset()
    unsupported_critical_claims: tuple[str, ...] = ()
    affordances: frozenset[str] = frozenset()
    evidence_events: frozenset[str] = frozenset()
    preferences_satisfied: frozenset[str] = frozenset()
    accessibility_capabilities: frozenset[str] = frozenset()
    depth: int = 0
    representation: str = ""
    support_policy: str = ""
    efficiency: EfficiencyMetrics | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.depth <= 4:
            raise ValueError("depth must be between 0 and 4")
        if self.declined and not (self.decline_reason or "").strip():
            raise ValueError("a declined observation needs a reason")


@dataclass(frozen=True, slots=True)
class GateFailure:
    code: GateCode
    ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SemanticSignature:
    """Catalogue-agnostic structure used for diversity/stability comparisons.

    Component names and layout wrappers are absent on purpose.  Two different widgets
    that provide the same learner action and evidence have the same signature.
    """

    affordances: tuple[str, ...]
    evidence_events: tuple[str, ...]
    representation: str
    support_policy: str
    depth: int

    def as_key(self) -> tuple[Any, ...]:
        return (
            self.affordances,
            self.evidence_events,
            self.representation,
            self.support_policy,
            self.depth,
        )


@dataclass(frozen=True, slots=True)
class QualityDimensions:
    affordance_coverage: float | None
    evidence_coverage: float | None
    preference_coverage: float | None
    accessibility_coverage: float | None
    depth_fit: float


@dataclass(frozen=True, slots=True)
class SelectionEvaluation:
    scenario_id: str
    gate_passed: bool
    gate_failures: tuple[GateFailure, ...]
    dimensions: QualityDimensions | None
    quality_score: float | None
    semantic_signature: SemanticSignature | None
    efficiency: EfficiencyMetrics | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


_DIMENSION_WEIGHTS = {
    "affordance_coverage": 0.30,
    "evidence_coverage": 0.30,
    "preference_coverage": 0.15,
    "accessibility_coverage": 0.15,
    "depth_fit": 0.10,
}


def _coverage(requirements: Iterable[WeightedRequirement], observed: set[str]) -> float | None:
    requirements = tuple(requirements)
    if not requirements:
        return None
    total = sum(item.weight for item in requirements)
    matched = sum(item.weight for item in requirements if item.id in observed)
    return matched / total


def _quality_score(dimensions: QualityDimensions) -> float:
    values = asdict(dimensions)
    applicable = {
        name: value for name, value in values.items() if value is not None
    }
    denominator = sum(_DIMENSION_WEIGHTS[name] for name in applicable)
    if not denominator:
        return 0.0
    score = sum(
        float(value) * _DIMENSION_WEIGHTS[name] for name, value in applicable.items()
    ) / denominator
    return round(score * 100.0, 2)


def evaluate_selection(
    expectations: SelectionExpectations,
    observation: SelectionObservation,
) -> SelectionEvaluation:
    """Evaluate one selection result without network, LLM calls or runtime state."""

    failures: list[GateFailure] = []
    expects_decline = expectations.expected_outcome is ExpectedOutcome.DECLINE
    expects_produce = expectations.expected_outcome is ExpectedOutcome.PRODUCE
    if (observation.declined and expects_produce) or (not observation.declined and expects_decline):
        failures.append(GateFailure(GateCode.OUTCOME_MISMATCH))

    # An expected/allowed honest decline has no course experience to score.
    if observation.declined:
        return SelectionEvaluation(
            scenario_id=expectations.scenario_id,
            gate_passed=not failures,
            gate_failures=tuple(failures),
            dimensions=None,
            quality_score=None,
            semantic_signature=None,
            efficiency=observation.efficiency,
        )

    if not observation.valid_spec:
        failures.append(GateFailure(GateCode.INVALID_SPEC))
    if not observation.fully_reachable:
        failures.append(GateFailure(GateCode.UNREACHABLE_CONTENT))

    critical_ids = {item.id for item in expectations.critical_facts}
    missing_facts = tuple(sorted(critical_ids - observation.facts_covered))
    contradicted = tuple(sorted(critical_ids & observation.facts_contradicted))
    if missing_facts:
        failures.append(GateFailure(GateCode.CRITICAL_FACT_MISSING, missing_facts))
    if contradicted:
        failures.append(GateFailure(GateCode.CRITICAL_FACT_CONTRADICTED, contradicted))
    if observation.unsupported_critical_claims:
        failures.append(
            GateFailure(
                GateCode.UNSUPPORTED_CRITICAL_CLAIM,
                tuple(observation.unsupported_critical_claims),
            )
        )
    if expectations.required_evidence and not observation.evaluation_grounded:
        failures.append(GateFailure(GateCode.EVALUATION_UNGROUNDED))

    required_accessibility = {item.id for item in expectations.required_accessibility}
    missing_accessibility = tuple(
        sorted(required_accessibility - observation.accessibility_capabilities)
    )
    if missing_accessibility:
        failures.append(
            GateFailure(GateCode.ACCESSIBILITY_REQUIRED_MISSING, missing_accessibility)
        )

    accessibility_by_id = {
        item.id: item
        for item in (*expectations.desired_accessibility, *expectations.required_accessibility)
    }
    desired_accessibility = tuple(accessibility_by_id.values())
    dimensions = QualityDimensions(
        affordance_coverage=_coverage(
            expectations.required_affordances, set(observation.affordances)
        ),
        evidence_coverage=_coverage(
            expectations.required_evidence, set(observation.evidence_events)
        ),
        preference_coverage=_coverage(
            expectations.applicable_preferences,
            set(observation.preferences_satisfied),
        ),
        accessibility_coverage=_coverage(
            desired_accessibility, set(observation.accessibility_capabilities)
        ),
        depth_fit=1.0 - abs(observation.depth - expectations.target_depth) / 4.0,
    )
    signature = SemanticSignature(
        affordances=tuple(sorted(observation.affordances)),
        evidence_events=tuple(sorted(observation.evidence_events)),
        representation=observation.representation,
        support_policy=observation.support_policy,
        depth=observation.depth,
    )
    gate_passed = not failures
    return SelectionEvaluation(
        scenario_id=expectations.scenario_id,
        gate_passed=gate_passed,
        gate_failures=tuple(failures),
        dimensions=dimensions,
        quality_score=_quality_score(dimensions) if gate_passed else None,
        semantic_signature=signature,
        efficiency=observation.efficiency,
    )
