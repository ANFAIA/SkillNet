"""Deterministic provider-neutral experience selection.

Design-time may prepare many valid bindings.  Runtime only applies hard capability
gates and a stable ranking; it never authors content or calls an LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ExperienceRequirements:
    intent: str
    learner_actions: frozenset[str] = frozenset()
    representations: frozenset[str] = frozenset()
    required_evidence: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class RuntimeExperienceContext:
    available_ports: frozenset[str] = frozenset()
    preferred_representations: frozenset[str] = frozenset()
    recent_implementation_refs: tuple[str, ...] = ()
    keyboard_required: bool = False
    screen_reader_required: bool = False
    low_bandwidth: bool = False
    max_latency_ms: int = 500
    max_cost_micros: int = 0


@dataclass(frozen=True, slots=True)
class ExperienceCandidate:
    binding_id: str
    implementation_ref: str
    provider: str
    intents: frozenset[str]
    learner_actions: frozenset[str]
    representations: frozenset[str]
    evidence: frozenset[str]
    required_ports: frozenset[str] = frozenset()
    enabled: bool = True
    keyboard: bool = True
    screen_reader: bool = True
    low_bandwidth: bool = True
    latency_ms: int = 0
    cost_micros: int = 0
    pedagogical_quality: float = 0.5
    evidence_quality: float = 0.5
    historical_effectiveness: float = 0.5
    is_fallback: bool = False


@dataclass(frozen=True, slots=True)
class CandidateRejection:
    binding_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class ResolvedExperience:
    candidates: tuple[ExperienceCandidate, ...]
    rejected: tuple[CandidateRejection, ...] = field(default_factory=tuple)

    @property
    def selected(self) -> ExperienceCandidate | None:
        return self.candidates[0] if self.candidates else None


def resolve_experience(
    requirements: ExperienceRequirements,
    candidates: list[ExperienceCandidate],
    context: RuntimeExperienceContext,
    *,
    shortlist_size: int = 3,
) -> ResolvedExperience:
    """Apply hard gates, then rank the surviving published bindings."""

    accepted: list[tuple[float, ExperienceCandidate]] = []
    rejected: list[CandidateRejection] = []
    recent = set(context.recent_implementation_refs)

    for candidate in candidates:
        reason = _rejection_reason(requirements, candidate, context)
        if reason is not None:
            rejected.append(CandidateRejection(candidate.binding_id, reason))
            continue
        representation_fit = bool(
            candidate.representations & context.preferred_representations
        )
        repeated = candidate.implementation_ref in recent
        score = (
            candidate.pedagogical_quality * 4
            + candidate.evidence_quality * 3
            + candidate.historical_effectiveness * 2
            + (0.5 if representation_fit else 0.0)
            - (0.35 if repeated else 0.0)
            - (0.05 if candidate.is_fallback else 0.0)
        )
        accepted.append((score, candidate))

    accepted.sort(key=lambda item: (-item[0], item[1].implementation_ref, item[1].binding_id))
    limit = max(1, shortlist_size)
    return ResolvedExperience(
        candidates=tuple(candidate for _score, candidate in accepted[:limit]),
        rejected=tuple(rejected),
    )


def _rejection_reason(
    requirements: ExperienceRequirements,
    candidate: ExperienceCandidate,
    context: RuntimeExperienceContext,
) -> str | None:
    if not candidate.enabled:
        return "disabled"
    if requirements.intent not in candidate.intents:
        return "intent"
    if not requirements.learner_actions.issubset(candidate.learner_actions):
        return "learner_actions"
    if requirements.representations and not (
        requirements.representations & candidate.representations
    ):
        return "representation"
    if not requirements.required_evidence.issubset(candidate.evidence):
        return "evidence"
    if not candidate.required_ports.issubset(context.available_ports):
        return "ports"
    if context.keyboard_required and not candidate.keyboard:
        return "keyboard"
    if context.screen_reader_required and not candidate.screen_reader:
        return "screen_reader"
    if context.low_bandwidth and not candidate.low_bandwidth:
        return "bandwidth"
    if candidate.latency_ms > context.max_latency_ms:
        return "latency"
    if candidate.cost_micros > context.max_cost_micros:
        return "cost"
    return None


__all__ = [
    "CandidateRejection",
    "ExperienceCandidate",
    "ExperienceRequirements",
    "ResolvedExperience",
    "RuntimeExperienceContext",
    "resolve_experience",
]
