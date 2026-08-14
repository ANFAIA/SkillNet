"""Pure capability filtering for runtime experience selection.

The broker knows neither screens nor provider component classes.  It receives a
small pedagogical/runtime requirement and returns a bounded set of implementations
that can satisfy it.  All constraints are hard gates; an optional catalogue
expansion adds candidates once, but never weakens a constraint.

The intended runtime chain has two deliberately separate decisions: this broker
filters implementation capabilities, then ``experience_resolver`` chooses a
published binding from that eligible set.  The module is not wired into that
production chain yet.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from src.personalization.didact_catalog import DidactCatalog
from src.schemas.episode_contracts import (
    CompetencyContract,
    EpisodeBrief,
    SourceAffordanceMap,
)

MIN_SHORTLIST = 1
MAX_SHORTLIST = 3


class CapabilityGate(StrEnum):
    """Ordered reasons for rejecting a capability implementation."""

    LEARNER_ACTION = "learner_action"
    EVIDENCE = "evidence"
    AFFORDANCE = "affordance"
    ACCESSIBILITY = "accessibility"
    SAFETY = "safety"
    PORTS = "ports"
    LATENCY = "latency"


@dataclass(frozen=True, slots=True)
class CapabilityDescriptor:
    """Provider implementation facts used by the broker.

    ``implementation_ref`` is an opaque provider boundary, not a pedagogical
    component name.  The remaining fields use product vocabulary shared by every
    delivery modality.
    """

    implementation_ref: str
    provider: str
    learner_actions: frozenset[str]
    evidence: frozenset[str]
    affordances: frozenset[str]
    accessibility: frozenset[str]
    safety: frozenset[str]
    required_ports: frozenset[str]
    latency_ms: int
    quality_rank: int = 100

    def __post_init__(self) -> None:
        if not self.implementation_ref.strip():
            raise ValueError("implementation_ref must not be empty")
        if not self.provider.strip():
            raise ValueError("provider must not be empty")
        if self.latency_ms < 0:
            raise ValueError("latency_ms must be non-negative")


@dataclass(frozen=True, slots=True)
class CapabilityRequest:
    """The minimum observable experience needed for one learning beat."""

    learner_actions: frozenset[str] = frozenset()
    evidence: frozenset[str] = frozenset()
    affordances: frozenset[str] = frozenset()
    accessibility: frozenset[str] = frozenset()
    safety: frozenset[str] = frozenset()
    available_ports: frozenset[str] = frozenset()
    latency_budget_ms: int = 500
    preferred_affordances: frozenset[str] = frozenset()
    shortlist_size: int = MAX_SHORTLIST

    def __post_init__(self) -> None:
        if self.latency_budget_ms < 0:
            raise ValueError("latency_budget_ms must be non-negative")
        if not MIN_SHORTLIST <= self.shortlist_size <= MAX_SHORTLIST:
            raise ValueError(
                f"shortlist_size must be between {MIN_SHORTLIST} and {MAX_SHORTLIST}"
            )


@dataclass(frozen=True, slots=True)
class GateFailure:
    gate: CapabilityGate
    candidate_count: int


@dataclass(frozen=True, slots=True)
class CapabilityShortlist:
    candidates: tuple[CapabilityDescriptor, ...]
    expanded: bool


@dataclass(frozen=True, slots=True)
class Declined:
    """No implementation survived the hard gates and one optional expansion."""

    eligible_count: int
    failures: tuple[GateFailure, ...]
    expanded: bool
    reason: str = "insufficient_capabilities"


CapabilityDecision = CapabilityShortlist | Declined
Expansion = Callable[[], Iterable[CapabilityDescriptor]]


class CapabilityBroker:
    """Deterministic hard-gate broker over a primary and optional expansion catalog."""

    def __init__(
        self,
        catalog: Iterable[CapabilityDescriptor],
        *,
        expand_once: Expansion | None = None,
    ) -> None:
        self._catalog = _unique_descriptors(catalog, reject_duplicates=True)
        self._expand_once = expand_once

    def resolve(self, request: CapabilityRequest) -> CapabilityDecision:
        accepted, failure_counts = _apply_gates(request, self._catalog)
        expanded = False

        if not accepted and self._expand_once is not None:
            expanded = True
            known_refs = {candidate.implementation_ref for candidate in self._catalog}
            expansion = _unique_descriptors(
                candidate
                for candidate in self._expand_once()
                if candidate.implementation_ref not in known_refs
            )
            more_accepted, more_failures = _apply_gates(request, expansion)
            accepted.extend(more_accepted)
            for gate, count in more_failures.items():
                failure_counts[gate] += count

        accepted.sort(key=lambda candidate: _rank_key(request, candidate))
        if not accepted:
            failures = tuple(
                GateFailure(gate=gate, candidate_count=failure_counts[gate])
                for gate in CapabilityGate
                if failure_counts[gate]
            )
            return Declined(
                eligible_count=len(accepted),
                failures=failures,
                expanded=expanded,
            )

        return CapabilityShortlist(
            candidates=tuple(accepted[: request.shortlist_size]),
            expanded=expanded,
        )


def descriptors_from_didact(
    catalog: DidactCatalog,
    *,
    safety_by_type: Mapping[str, frozenset[str]] | None = None,
    latency_by_type: Mapping[str, int] | None = None,
    default_latency_ms: int = 100,
) -> tuple[CapabilityDescriptor, ...]:
    """Project the installed Didact inventory without inventing missing guarantees.

    Didact capabilities beginning with ``result:`` are observable evidence; the
    remaining capabilities are interaction affordances.  Safety is only included
    when a host-owned catalogue overlay explicitly declares it.
    """

    if default_latency_ms < 0:
        raise ValueError("default_latency_ms must be non-negative")
    safety_by_type = safety_by_type or {}
    latency_by_type = latency_by_type or {}
    descriptors: list[CapabilityDescriptor] = []
    for component in catalog.emittable:
        accessibility = {
            f"wcag:{criterion}" for criterion in component.wcag_criteria
        }
        if component.keyboard_access in {"full", "alternative"}:
            accessibility.add("keyboard")
        if component.screen_reader_access in {"full", "alternative"}:
            accessibility.add("screen_reader")
        evidence = frozenset(
            capability
            for capability in component.capabilities
            if capability.startswith("result:")
        )
        affordances = frozenset(
            capability
            for capability in component.capabilities
            if not capability.startswith("result:")
        )
        descriptors.append(
            CapabilityDescriptor(
                implementation_ref=f"{component.type_id}@{component.component_version}",
                provider="didact",
                learner_actions=frozenset(component.learner_actions),
                evidence=evidence,
                affordances=affordances,
                accessibility=frozenset(accessibility),
                safety=safety_by_type.get(component.type_id, frozenset()),
                required_ports=frozenset(str(port) for port in component.required_ports),
                latency_ms=latency_by_type.get(component.type_id, default_latency_ms),
            )
        )
    return tuple(descriptors)


def request_from_episode(
    competency: CompetencyContract,
    sources: SourceAffordanceMap,
    episode: EpisodeBrief,
    *,
    accessibility: frozenset[str],
    safety: frozenset[str],
    available_ports: frozenset[str],
    shortlist_size: int = MAX_SHORTLIST,
) -> CapabilityRequest:
    """Project validated episode truth into the broker's narrow selection view.

    Safety, accessibility and ports remain explicit host policy.  In particular,
    criticality is not silently translated into a provider guarantee.
    """

    evidence_by_id = {gate.gate_id: gate.evidence_type for gate in competency.evidence_gates}
    affordance_by_id = {
        affordance.affordance_id: affordance.kind for affordance in sources.affordances
    }
    return CapabilityRequest(
        learner_actions=frozenset({episode.dominant_action.verb}),
        evidence=frozenset(evidence_by_id[ref] for ref in episode.evidence_gate_refs),
        affordances=frozenset(affordance_by_id[ref] for ref in episode.affordance_refs),
        accessibility=accessibility,
        safety=safety,
        available_ports=available_ports,
        latency_budget_ms=episode.budget.latency_budget_ms,
        shortlist_size=shortlist_size,
    )


def _apply_gates(
    request: CapabilityRequest,
    candidates: Iterable[CapabilityDescriptor],
) -> tuple[list[CapabilityDescriptor], dict[CapabilityGate, int]]:
    accepted: list[CapabilityDescriptor] = []
    failures = dict.fromkeys(CapabilityGate, 0)
    for candidate in candidates:
        failed = _failed_gates(request, candidate)
        if failed:
            for gate in failed:
                failures[gate] += 1
        else:
            accepted.append(candidate)
    return accepted, failures


def _unique_descriptors(
    candidates: Iterable[CapabilityDescriptor],
    *,
    reject_duplicates: bool = False,
) -> tuple[CapabilityDescriptor, ...]:
    unique: list[CapabilityDescriptor] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate.implementation_ref in seen:
            if reject_duplicates:
                raise ValueError(
                    f"duplicate implementation_ref: {candidate.implementation_ref}"
                )
            continue
        seen.add(candidate.implementation_ref)
        unique.append(candidate)
    return tuple(unique)


def _failed_gates(
    request: CapabilityRequest,
    candidate: CapabilityDescriptor,
) -> tuple[CapabilityGate, ...]:
    failed: list[CapabilityGate] = []
    checks = (
        (CapabilityGate.LEARNER_ACTION, request.learner_actions, candidate.learner_actions),
        (CapabilityGate.EVIDENCE, request.evidence, candidate.evidence),
        (CapabilityGate.AFFORDANCE, request.affordances, candidate.affordances),
        (
            CapabilityGate.ACCESSIBILITY,
            request.accessibility,
            candidate.accessibility,
        ),
        (CapabilityGate.SAFETY, request.safety, candidate.safety),
        (CapabilityGate.PORTS, candidate.required_ports, request.available_ports),
    )
    for gate, required, available in checks:
        if not required.issubset(available):
            failed.append(gate)
    if candidate.latency_ms > request.latency_budget_ms:
        failed.append(CapabilityGate.LATENCY)
    return tuple(failed)


def _rank_key(
    request: CapabilityRequest,
    candidate: CapabilityDescriptor,
) -> tuple[int, int, int, str]:
    preferred_coverage = len(request.preferred_affordances & candidate.affordances)
    return (
        -preferred_coverage,
        candidate.quality_rank,
        candidate.latency_ms,
        candidate.implementation_ref,
    )


__all__ = [
    "CapabilityBroker",
    "CapabilityDecision",
    "CapabilityDescriptor",
    "CapabilityGate",
    "CapabilityRequest",
    "CapabilityShortlist",
    "Declined",
    "GateFailure",
    "descriptors_from_didact",
    "request_from_episode",
]
