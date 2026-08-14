"""Pure policy for building grounded learning episode briefs on demand.

The policy chooses an instructional strategy and a source capability.  It does not
choose a renderer, component, provider, or persisted artifact.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Callable

from src.schemas.episode_contracts import (
    CompetencyContract,
    CompetencyRef,
    ContinuationCondition,
    DominantAction,
    EpisodeBrief,
    EpisodeBudget,
    LearnerBeliefSnapshot,
    SourceAffordance,
    SourceAffordanceMap,
    validate_episode_contracts,
)

_EPISODE_NAMESPACE = uuid.UUID("a1b6cbd7-49d6-51ef-972f-d8cd53b25476")
_FIDELITY_ORDER = {"exact": 0, "derived": 1, "synthetic": 2}


StrategyMatcher = Callable[[CompetencyContract, LearnerBeliefSnapshot], bool]


@dataclass(frozen=True)
class EpisodeStrategy:
    """Injectable recipe that selects intent without prescribing its rendering."""

    name: str
    matcher: StrategyMatcher
    reason: str
    preferred_actions: tuple[str, ...]
    action_terms: tuple[str, ...]
    instruction: str
    budget: EpisodeBudget

    def matches(
        self,
        competency: CompetencyContract,
        belief: LearnerBeliefSnapshot,
    ) -> bool:
        return self.matcher(competency, belief)

    def choose(self, source_map: SourceAffordanceMap) -> tuple[SourceAffordance, str, bool]:
        """Choose only among capabilities explicitly declared by the source map."""

        affordances = _ordered_affordances(source_map)
        for preferred in self.preferred_actions:
            for affordance in affordances:
                if preferred in affordance.supports_actions:
                    return affordance, preferred, False

        for affordance in affordances:
            for action in affordance.supports_actions:
                normalized = action.casefold()
                if any(term in normalized for term in self.action_terms):
                    return affordance, action, False

        fallback = affordances[0]
        return fallback, sorted(fallback.supports_actions)[0], True


def _domain_has(*terms: str) -> StrategyMatcher:
    def matches(
        competency: CompetencyContract,
        _belief: LearnerBeliefSnapshot,
    ) -> bool:
        domain = competency.domain.casefold()
        return any(term in domain for term in terms)

    return matches


def _with_errors(domain_matcher: StrategyMatcher) -> StrategyMatcher:
    def matches(
        competency: CompetencyContract,
        belief: LearnerBeliefSnapshot,
    ) -> bool:
        return domain_matcher(competency, belief) and bool(belief.recent_error_kinds)

    return matches


def _without_errors(domain_matcher: StrategyMatcher) -> StrategyMatcher:
    def matches(
        competency: CompetencyContract,
        belief: LearnerBeliefSnapshot,
    ) -> bool:
        return domain_matcher(competency, belief) and not belief.recent_error_kinds

    return matches


def _ticket_novice(
    competency: CompetencyContract,
    belief: LearnerBeliefSnapshot,
) -> bool:
    return _TICKET_DOMAIN(competency, belief) and not belief.recent_error_kinds and _is_novice(
        belief
    )


def _ticket_experienced(
    competency: CompetencyContract,
    belief: LearnerBeliefSnapshot,
) -> bool:
    return (
        _TICKET_DOMAIN(competency, belief)
        and not belief.recent_error_kinds
        and not _is_novice(belief)
    )


def _always(
    _competency: CompetencyContract,
    _belief: LearnerBeliefSnapshot,
) -> bool:
    return True


_TICKET_DOMAIN = _domain_has("ticket", "support", "event")
_SQL_DOMAIN = _domain_has("sql", "database")


_TICKET_ACTION = EpisodeStrategy(
    name="ticket-action-first",
    matcher=_ticket_experienced,
    reason="sufficient-prior-experience",
    preferred_actions=("recover_ticket", "resolve_ticket", "complete_case"),
    action_terms=("recover", "resolve", "ticket", "case"),
    instruction="Resolve the grounded case and submit evidence of the resulting state.",
    budget=EpisodeBudget(
        max_content_units=2,
        max_interaction_steps=8,
        max_words=220,
        latency_budget_ms=1800,
    ),
)
_TICKET_ERROR_GUIDE = EpisodeStrategy(
    name="ticket-guided-recovery",
    matcher=_with_errors(_TICKET_DOMAIN),
    reason="recent-error",
    preferred_actions=(
        "recover_ticket_guided",
        "follow_recovery_guide",
        "inspect_recovery_guide",
    ),
    action_terms=("guide", "guided", "inspect", "recovery", "recover"),
    instruction=(
        "Use the grounded procedure to work through the case, checking the unsafe "
        "states before submitting evidence."
    ),
    budget=EpisodeBudget(
        max_content_units=5,
        max_interaction_steps=14,
        max_words=650,
        latency_budget_ms=2200,
    ),
)
_TICKET_NOVICE_GUIDE = EpisodeStrategy(
    name="ticket-guided-recovery",
    matcher=_ticket_novice,
    reason="limited-prior-experience",
    preferred_actions=_TICKET_ERROR_GUIDE.preferred_actions,
    action_terms=_TICKET_ERROR_GUIDE.action_terms,
    instruction=_TICKET_ERROR_GUIDE.instruction,
    budget=_TICKET_ERROR_GUIDE.budget,
)
_SQL_CONSTRUCT = EpisodeStrategy(
    name="sql-construct",
    matcher=_without_errors(_SQL_DOMAIN),
    reason="constructive-practice",
    preferred_actions=("construct_query", "write_query", "execute_query"),
    action_terms=("construct", "write", "query", "sql"),
    instruction="Construct a query for the grounded data task and submit its execution evidence.",
    budget=EpisodeBudget(
        max_content_units=3,
        max_interaction_steps=10,
        max_words=320,
        latency_budget_ms=1800,
    ),
)
_SQL_DEBUG = EpisodeStrategy(
    name="sql-debug",
    matcher=_with_errors(_SQL_DOMAIN),
    reason="recent-error",
    preferred_actions=("debug_query", "repair_query", "diagnose_query"),
    action_terms=("debug", "repair", "diagnose", "fix"),
    instruction="Diagnose the failing query, correct it, and submit evidence from the new result.",
    budget=EpisodeBudget(
        max_content_units=4,
        max_interaction_steps=16,
        max_words=450,
        latency_budget_ms=2000,
    ),
)
GENERIC_EPISODE_STRATEGY = EpisodeStrategy(
    name="grounded-action",
    matcher=_always,
    reason="domain-neutral-fallback",
    preferred_actions=(),
    action_terms=(),
    instruction="Perform the grounded task and submit evidence of the outcome.",
    budget=EpisodeBudget(
        max_content_units=3,
        max_interaction_steps=10,
        max_words=350,
        latency_budget_ms=2000,
    ),
)

DEFAULT_EPISODE_STRATEGIES: tuple[EpisodeStrategy, ...] = (
    _TICKET_ERROR_GUIDE,
    _TICKET_NOVICE_GUIDE,
    _TICKET_ACTION,
    _SQL_DEBUG,
    _SQL_CONSTRUCT,
)


def _is_novice(belief: LearnerBeliefSnapshot) -> bool:
    level = belief.experience_level.casefold()
    return belief.mastery < 0.4 or any(
        term in level for term in ("novice", "beginner", "new", "inicial")
    )


def _select_strategy(
    competency: CompetencyContract,
    belief: LearnerBeliefSnapshot,
    strategies: tuple[EpisodeStrategy, ...],
) -> EpisodeStrategy:
    registry = strategies + (GENERIC_EPISODE_STRATEGY,)
    return next(strategy for strategy in registry if strategy.matches(competency, belief))


def _ordered_affordances(source_map: SourceAffordanceMap) -> tuple[SourceAffordance, ...]:
    return tuple(
        sorted(
            source_map.affordances,
            key=lambda item: (_FIDELITY_ORDER[item.fidelity], item.affordance_id),
        )
    )


def _episode_uuid(
    competency: CompetencyContract,
    source_map: SourceAffordanceMap,
    belief: LearnerBeliefSnapshot,
    strategy_name: str,
    action: str,
) -> uuid.UUID:
    identity = json.dumps(
        {
            "action": action,
            "belief": belief.state_digest,
            "competency_id": competency.competency_id,
            "competency_version": competency.version,
            "grounding_digest": source_map.map_digest,
            "grounding_version": source_map.version,
            "strategy": strategy_name,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return uuid.uuid5(_EPISODE_NAMESPACE, identity)


def _continuations(
    competency: CompetencyContract,
) -> tuple[ContinuationCondition, ...]:
    required_gates = tuple(gate.gate_id for gate in competency.evidence_gates if gate.required)
    conditions: list[ContinuationCondition] = [
        ContinuationCondition(
            condition_id="required-evidence-satisfied",
            kind="evidence_satisfied",
            destination_state="competency-complete",
            evidence_gate_refs=required_gates,
            priority=10,
        )
    ]
    conditions.extend(
        ContinuationCondition(
            condition_id=f"recover-{error.error_id}",
            kind="critical_error_detected",
            destination_state=error.recovery_state,
            critical_error_refs=(error.error_id,),
            priority=20 + index,
        )
        for index, error in enumerate(competency.critical_errors)
    )
    conditions.append(
        ContinuationCondition(
            condition_id="continue-adaptation",
            kind="always",
            destination_state="next-episode",
            priority=1000,
            is_default=True,
        )
    )
    return tuple(conditions)


def build_episode_brief(
    competency: CompetencyContract,
    source_map: SourceAffordanceMap,
    belief: LearnerBeliefSnapshot,
    strategies: tuple[EpisodeStrategy, ...] | None = None,
) -> EpisodeBrief:
    """Build and cross-validate one deterministic episode brief from current state."""

    registry = DEFAULT_EPISODE_STRATEGIES if strategies is None else strategies
    strategy = _select_strategy(competency, belief, registry)
    affordance, action, used_fallback = strategy.choose(source_map)
    required_gates = tuple(gate for gate in competency.evidence_gates if gate.required)
    evidence_refs = tuple(gate.gate_id for gate in required_gates)
    critical_refs = tuple(error.error_id for error in competency.critical_errors)
    source_refs = set(competency.required_fact_refs)
    source_refs.update(affordance.source_refs)
    for gate in required_gates:
        source_refs.update(gate.source_refs)
    for error in competency.critical_errors:
        source_refs.update(error.source_refs)

    brief = EpisodeBrief(
        episode_id=_episode_uuid(competency, source_map, belief, strategy.name, action),
        version=1,
        competency_ref=CompetencyRef(
            competency_id=competency.competency_id,
            version=competency.version,
        ),
        belief_snapshot=belief,
        grounding_map_id=source_map.map_id,
        grounding_map_version=source_map.version,
        grounding_digest=source_map.map_digest,
        source_refs=tuple(sorted(source_refs)),
        affordance_refs=(affordance.affordance_id,),
        dominant_action=DominantAction(
            action_id=f"{strategy.name}:{action}",
            verb=action,
            target=competency.outcome,
            submission_kind=required_gates[0].evidence_type,
            instructions=strategy.instruction,
            constraints={"critical_error_refs": list(critical_refs)},
        ),
        assessment_mode="summative" if belief.mastery >= 0.65 else "formative",
        evidence_gate_refs=evidence_refs,
        critical_error_refs=critical_refs,
        budget=strategy.budget,
        continuation_conditions=_continuations(competency),
        policy_trace={
            "strategy": strategy.name,
            "reason": strategy.reason,
            "capability_fallback": used_fallback,
        },
    )
    validate_episode_contracts(competency, source_map, brief)
    return brief


def build_support_episode_brief(
    competency: CompetencyContract,
    source_map: SourceAffordanceMap,
    belief: LearnerBeliefSnapshot,
    *,
    decline_reason: str,
) -> EpisodeBrief:
    """Build grounded, explicitly unscored support when no real oracle is available."""

    if not decline_reason.strip():
        raise ValueError("support decline_reason must not be empty")
    registry = DEFAULT_EPISODE_STRATEGIES
    strategy = _select_strategy(competency, belief, registry)
    affordance, action, used_fallback = strategy.choose(source_map)
    critical_refs = tuple(error.error_id for error in competency.critical_errors)
    source_refs = set(competency.required_fact_refs)
    source_refs.update(affordance.source_refs)
    for error in competency.critical_errors:
        source_refs.update(error.source_refs)
    continuations = [
        ContinuationCondition(
            condition_id=f"support-recover-{error.error_id}",
            kind="critical_error_detected",
            destination_state=error.recovery_state,
            critical_error_refs=(error.error_id,),
            priority=20 + index,
        )
        for index, error in enumerate(competency.critical_errors)
    ]
    continuations.extend(
        (
            ContinuationCondition(
                condition_id="request-more-support",
                kind="learner_request",
                destination_state="next-support",
                priority=100,
            ),
            ContinuationCondition(
                condition_id="continue-support",
                kind="always",
                destination_state="next-support",
                priority=1000,
                is_default=True,
            ),
        )
    )
    brief = EpisodeBrief(
        episode_id=_episode_uuid(
            competency,
            source_map,
            belief,
            f"support-only:{decline_reason}:{strategy.name}",
            action,
        ),
        version=1,
        competency_ref=CompetencyRef(
            competency_id=competency.competency_id,
            version=competency.version,
        ),
        belief_snapshot=belief,
        grounding_map_id=source_map.map_id,
        grounding_map_version=source_map.version,
        grounding_digest=source_map.map_digest,
        source_refs=tuple(sorted(source_refs)),
        affordance_refs=(affordance.affordance_id,),
        dominant_action=DominantAction(
            action_id=f"support-only:{strategy.name}:{action}",
            verb=action,
            target=competency.outcome,
            submission_kind="unscored-support-interaction",
            instructions=(
                "Use the grounded material to rehearse the task. This support episode "
                "does not submit scored evidence or establish mastery."
            ),
            constraints={"critical_error_refs": list(critical_refs)},
        ),
        assessment_mode="none",
        evidence_gate_refs=(),
        critical_error_refs=critical_refs,
        budget=strategy.budget,
        continuation_conditions=tuple(continuations),
        policy_trace={
            "strategy": strategy.name,
            "reason": decline_reason,
            "degraded_mode": "support_only",
            "unscored": True,
            "evidence_blocked": True,
            "mastery_blocked": True,
            "capability_fallback": used_fallback,
        },
    )
    validate_episode_contracts(competency, source_map, brief)
    return brief


def degrade_episode_brief_to_support(
    episode: EpisodeBrief,
    *,
    decline_reason: str,
) -> EpisodeBrief:
    """Remove scoring from an already-grounded brief when authoring cannot be grounded."""

    if not decline_reason.strip():
        raise ValueError("support decline_reason must not be empty")
    critical_conditions = tuple(
        condition
        for condition in episode.continuation_conditions
        if condition.kind == "critical_error_detected"
    )
    support_conditions = (
        ContinuationCondition(
            condition_id="request-more-support",
            kind="learner_request",
            destination_state="next-support",
            priority=100,
        ),
        ContinuationCondition(
            condition_id="continue-support",
            kind="always",
            destination_state="next-support",
            priority=1000,
            is_default=True,
        ),
    )
    payload = episode.model_dump(mode="python")
    payload.update(
        {
            "episode_id": uuid.uuid5(
                _EPISODE_NAMESPACE,
                f"{episode.episode_id}:support-only:{decline_reason}",
            ),
            "assessment_mode": "none",
            "evidence_gate_refs": (),
            "dominant_action": episode.dominant_action.model_copy(
                update={
                    "submission_kind": "unscored-support-interaction",
                    "instructions": (
                        "Use the grounded material to rehearse the task. This support "
                        "episode does not submit scored evidence or establish mastery."
                    ),
                }
            ),
            "continuation_conditions": (*critical_conditions, *support_conditions),
            "policy_trace": {
                **episode.policy_trace,
                "reason": decline_reason,
                "degraded_mode": "support_only",
                "unscored": True,
                "evidence_blocked": True,
                "mastery_blocked": True,
            },
        }
    )
    return EpisodeBrief.model_validate(payload)


__all__ = [
    "DEFAULT_EPISODE_STRATEGIES",
    "GENERIC_EPISODE_STRATEGY",
    "EpisodeStrategy",
    "build_episode_brief",
    "build_support_episode_brief",
    "degrade_episode_brief_to_support",
]
