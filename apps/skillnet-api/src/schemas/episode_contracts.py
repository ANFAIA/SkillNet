"""Minimal, provider-neutral contracts for runtime learning episodes.

These contracts fix domain truth, source affordances and safety/evidence boundaries.
They deliberately do not prescribe screens, pedagogical slots, providers or render
components.  Persistence and runtime adoption are separate rollout decisions.
"""

from __future__ import annotations

import re
import uuid
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

_OPAQUE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,239}$")
_RESERVED_ARCHITECTURE_KEYS = frozenset(
    {
        "block",
        "block_id",
        "component",
        "component_id",
        "concept",
        "implementation",
        "implementation_id",
        "lead",
        "practice",
        "provider",
        "provider_id",
        "slot",
        "slots",
    }
)


def _unique_non_empty(values: tuple[str, ...]) -> tuple[str, ...]:
    cleaned = tuple(value.strip() for value in values)
    if any(not value for value in cleaned):
        raise ValueError("references and capabilities must be non-empty")
    if len(cleaned) != len(set(cleaned)):
        raise ValueError("references and capabilities must be unique")
    return cleaned


StringRefs = Annotated[tuple[str, ...], AfterValidator(_unique_non_empty)]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def _assert_neutral_tree(value: Any, path: str) -> Any:
    """Reject concrete render architecture hidden inside extensible metadata."""

    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key).strip().lower()
            if key in _RESERVED_ARCHITECTURE_KEYS:
                raise ValueError(f"{path}.{raw_key} is render-specific")
            _assert_neutral_tree(child, f"{path}.{raw_key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_neutral_tree(child, f"{path}[{index}]")
    return value


class FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CompetencyRef(FrozenContract):
    competency_id: str = Field(min_length=1, max_length=200)
    version: int = Field(ge=1)


class SourceProvenance(FrozenContract):
    """Opaque, reproducible pointer to source material; never copied credentials."""

    # Knowledge packs deliberately use opaque document identifiers: production UUIDs,
    # fixture ids and imported-system ids all cross the same boundary.  Requiring UUID
    # here would either discard valid provenance or force the runtime to fabricate one.
    document_id: str = Field(min_length=1, max_length=240, pattern=_OPAQUE_REF.pattern)
    origin_ref: str = Field(min_length=1, max_length=240)
    revision: str = Field(min_length=1, max_length=120)
    locator: str = Field(min_length=1, max_length=500)
    content_digest: Sha256

    @field_validator("document_id", mode="before")
    @classmethod
    def normalize_document_id(cls, value: Any) -> str:
        return str(value)


class EvidenceGate(FrozenContract):
    gate_id: str = Field(min_length=1, max_length=160)
    evidence_type: str = Field(min_length=1, max_length=160)
    oracle_ref: str = Field(min_length=1, max_length=240)
    source_refs: StringRefs = Field(min_length=1)
    minimum_score: float | None = Field(default=None, ge=0.0, le=1.0)
    required: bool = True
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("attributes")
    @classmethod
    def neutral_attributes(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _assert_neutral_tree(value, "attributes")


class CriticalError(FrozenContract):
    error_id: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=1000)
    source_refs: StringRefs = Field(min_length=1)
    blocking: bool = True
    recovery_state: str = Field(min_length=1, max_length=160)


class CompetencyContract(FrozenContract):
    """Stable business outcome and its server-verifiable evidence boundary."""

    schema_version: Literal[1] = 1
    competency_id: str = Field(min_length=1, max_length=200)
    version: int = Field(ge=1)
    domain: str = Field(min_length=1, max_length=160)
    outcome: str = Field(min_length=1, max_length=1000)
    criticality: Literal["critical", "recommended", "contextual"]
    required_fact_refs: StringRefs = Field(min_length=1)
    prerequisite_refs: StringRefs = ()
    evidence_gates: tuple[EvidenceGate, ...] = Field(min_length=1)
    critical_errors: tuple[CriticalError, ...] = ()
    mastery_policy_ref: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def coherent_safety_and_evidence(self) -> CompetencyContract:
        gate_ids = [gate.gate_id for gate in self.evidence_gates]
        if len(gate_ids) != len(set(gate_ids)):
            raise ValueError("evidence gate ids must be unique")
        error_ids = [error.error_id for error in self.critical_errors]
        if len(error_ids) != len(set(error_ids)):
            raise ValueError("critical error ids must be unique")
        if not any(gate.required for gate in self.evidence_gates):
            raise ValueError("at least one evidence gate must be required")
        if self.criticality == "critical":
            if not self.critical_errors:
                raise ValueError("critical competency needs explicit critical errors")
            if not all(error.blocking for error in self.critical_errors):
                raise ValueError("critical competency errors must block progression")
        return self


class SourceAffordance(FrozenContract):
    """What grounded source material permits a learner to inspect or do."""

    affordance_id: str = Field(min_length=1, max_length=160)
    kind: str = Field(min_length=1, max_length=160)
    source_refs: StringRefs = Field(min_length=1)
    supports_actions: StringRefs = Field(min_length=1)
    fidelity: Literal["exact", "derived", "synthetic"]
    runtime_requirements: dict[str, Any] = Field(default_factory=dict)

    @field_validator("runtime_requirements")
    @classmethod
    def neutral_requirements(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _assert_neutral_tree(value, "runtime_requirements")


class SourceAffordanceMap(FrozenContract):
    """Versioned grounding inventory available to runtime episode generation."""

    schema_version: Literal[1] = 1
    map_id: str = Field(min_length=1, max_length=200)
    version: int = Field(ge=1)
    competency_ref: CompetencyRef
    source_refs: dict[str, SourceProvenance] = Field(min_length=1)
    affordances: tuple[SourceAffordance, ...] = Field(min_length=1)
    map_digest: Sha256

    @model_validator(mode="after")
    def references_exist(self) -> SourceAffordanceMap:
        known_sources = set(self.source_refs)
        if any(not _OPAQUE_REF.fullmatch(ref) for ref in known_sources):
            raise ValueError("source ref ids must be bounded opaque identifiers")
        affordance_ids = [item.affordance_id for item in self.affordances]
        if len(affordance_ids) != len(set(affordance_ids)):
            raise ValueError("affordance ids must be unique")
        for affordance in self.affordances:
            missing = set(affordance.source_refs) - known_sources
            if missing:
                raise ValueError(
                    f"affordance {affordance.affordance_id!r} has unknown source refs: "
                    f"{sorted(missing)}"
                )
        return self


class LearnerBeliefSnapshot(FrozenContract):
    mastery: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    recent_error_kinds: StringRefs = ()
    hints_used: int = Field(default=0, ge=0)
    experience_level: str = Field(min_length=1, max_length=100)
    state_digest: Sha256


class DominantAction(FrozenContract):
    """Exactly one primary learner action; no prescribed widget or component."""

    action_id: str = Field(min_length=1, max_length=160)
    verb: str = Field(min_length=1, max_length=120)
    target: str = Field(min_length=1, max_length=500)
    submission_kind: str = Field(min_length=1, max_length=160)
    instructions: str = Field(min_length=1, max_length=1200)
    constraints: dict[str, Any] = Field(default_factory=dict)

    @field_validator("constraints")
    @classmethod
    def neutral_constraints(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _assert_neutral_tree(value, "constraints")


class EpisodeBudget(FrozenContract):
    """Resource envelope, not a layout recipe."""

    max_primary_actions: Literal[1] = 1
    max_content_units: int = Field(ge=1, le=20)
    max_interaction_steps: int = Field(ge=1, le=50)
    max_words: int | None = Field(default=None, ge=20, le=5000)
    max_media_seconds: int | None = Field(default=None, ge=1, le=14400)
    latency_budget_ms: int = Field(ge=50, le=120000)


class ContinuationCondition(FrozenContract):
    condition_id: str = Field(min_length=1, max_length=160)
    kind: Literal[
        "always",
        "evidence_satisfied",
        "critical_error_detected",
        "learner_request",
    ]
    destination_state: str = Field(min_length=1, max_length=160)
    evidence_gate_refs: StringRefs = ()
    critical_error_refs: StringRefs = ()
    priority: int = Field(ge=0, le=1000)
    is_default: bool = False

    @model_validator(mode="after")
    def condition_matches_kind(self) -> ContinuationCondition:
        if self.kind == "evidence_satisfied" and not self.evidence_gate_refs:
            raise ValueError("evidence continuation needs evidence_gate_refs")
        if self.kind == "critical_error_detected" and not self.critical_error_refs:
            raise ValueError("critical-error continuation needs critical_error_refs")
        if self.kind in {"always", "learner_request"} and (
            self.evidence_gate_refs or self.critical_error_refs
        ):
            raise ValueError(f"{self.kind} continuation cannot carry gate refs")
        if self.is_default and self.kind != "always":
            raise ValueError("the default continuation must use kind='always'")
        return self


class EpisodeBrief(FrozenContract):
    """One runtime learning beat, free of screen formulas and provider ids."""

    schema_version: Literal[1] = 1
    episode_id: uuid.UUID
    version: int = Field(ge=1)
    competency_ref: CompetencyRef
    belief_snapshot: LearnerBeliefSnapshot
    grounding_map_id: str = Field(min_length=1, max_length=200)
    grounding_map_version: int = Field(ge=1)
    grounding_digest: Sha256
    source_refs: StringRefs = Field(min_length=1)
    affordance_refs: StringRefs = Field(min_length=1)
    dominant_action: DominantAction
    assessment_mode: Literal["none", "formative", "summative"]
    evidence_gate_refs: StringRefs = ()
    critical_error_refs: StringRefs = ()
    budget: EpisodeBudget
    continuation_conditions: tuple[ContinuationCondition, ...] = Field(min_length=1)
    policy_trace: dict[str, Any] = Field(default_factory=dict)

    @field_validator("policy_trace")
    @classmethod
    def neutral_policy_trace(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _assert_neutral_tree(value, "policy_trace")

    @model_validator(mode="after")
    def coherent_episode_flow(self) -> EpisodeBrief:
        condition_ids = [item.condition_id for item in self.continuation_conditions]
        if len(condition_ids) != len(set(condition_ids)):
            raise ValueError("continuation condition ids must be unique")
        defaults = [item for item in self.continuation_conditions if item.is_default]
        if len(defaults) != 1:
            raise ValueError("episode needs exactly one default continuation")
        if self.assessment_mode == "none":
            if self.evidence_gate_refs:
                raise ValueError("unassessed episode cannot require evidence gates")
            if any(
                item.kind == "evidence_satisfied"
                for item in self.continuation_conditions
            ):
                raise ValueError("unassessed episode cannot branch on evidence")
        else:
            if not self.evidence_gate_refs:
                raise ValueError("assessed episode needs evidence_gate_refs")
            covered = {
                ref
                for item in self.continuation_conditions
                if item.kind == "evidence_satisfied"
                for ref in item.evidence_gate_refs
            }
            if not set(self.evidence_gate_refs).issubset(covered):
                raise ValueError("every episode evidence gate needs a continuation")
        covered_errors = {
            ref
            for item in self.continuation_conditions
            if item.kind == "critical_error_detected"
            for ref in item.critical_error_refs
        }
        if not set(self.critical_error_refs).issubset(covered_errors):
            raise ValueError("every episode critical error needs a recovery continuation")
        return self


def validate_episode_contracts(
    competency: CompetencyContract,
    sources: SourceAffordanceMap,
    episode: EpisodeBrief,
) -> None:
    """Validate references spanning the three independently versioned contracts."""

    expected_ref = CompetencyRef(
        competency_id=competency.competency_id,
        version=competency.version,
    )
    if sources.competency_ref != expected_ref or episode.competency_ref != expected_ref:
        raise ValueError("competency refs must resolve to the same contract version")
    if (
        episode.grounding_map_id != sources.map_id
        or episode.grounding_map_version != sources.version
        or episode.grounding_digest != sources.map_digest
    ):
        raise ValueError("episode must pin the exact source affordance map")

    known_sources = set(sources.source_refs)
    competency_sources = set(competency.required_fact_refs)
    for gate in competency.evidence_gates:
        competency_sources.update(gate.source_refs)
    for error in competency.critical_errors:
        competency_sources.update(error.source_refs)
    missing_contract_sources = competency_sources - known_sources
    if missing_contract_sources:
        raise ValueError(
            f"competency references unknown sources: {sorted(missing_contract_sources)}"
        )
    if not set(episode.source_refs).issubset(known_sources):
        raise ValueError("episode contains unknown source refs")

    affordances = {item.affordance_id: item for item in sources.affordances}
    if not set(episode.affordance_refs).issubset(affordances):
        raise ValueError("episode contains unknown affordance refs")
    selected = [affordances[ref] for ref in episode.affordance_refs]
    selected_sources = {
        source_ref for affordance in selected for source_ref in affordance.source_refs
    }
    if not selected_sources.issubset(episode.source_refs):
        raise ValueError("episode must pin every source backing its affordances")
    supported_actions = {
        action for affordance in selected for action in affordance.supports_actions
    }
    if episode.dominant_action.verb not in supported_actions:
        raise ValueError("dominant action is unsupported by selected affordances")

    known_gates = {gate.gate_id for gate in competency.evidence_gates}
    if not set(episode.evidence_gate_refs).issubset(known_gates):
        raise ValueError("episode contains unknown evidence gate refs")
    known_errors = {error.error_id for error in competency.critical_errors}
    if not set(episode.critical_error_refs).issubset(known_errors):
        raise ValueError("episode contains unknown critical error refs")


__all__ = [
    "CompetencyContract",
    "CompetencyRef",
    "ContinuationCondition",
    "CriticalError",
    "DominantAction",
    "EpisodeBrief",
    "EpisodeBudget",
    "EvidenceGate",
    "LearnerBeliefSnapshot",
    "SourceAffordance",
    "SourceAffordanceMap",
    "SourceProvenance",
    "validate_episode_contracts",
]
