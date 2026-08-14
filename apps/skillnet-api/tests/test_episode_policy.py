from __future__ import annotations

import uuid

import pytest

from src.schemas.episode_contracts import (
    CompetencyContract,
    CompetencyRef,
    CriticalError,
    EvidenceGate,
    LearnerBeliefSnapshot,
    SourceAffordance,
    SourceAffordanceMap,
    SourceProvenance,
)
from src.schemas.episode_contracts import EpisodeBudget
from src.services.episode_policy import EpisodeStrategy, build_episode_brief

SOURCE_DIGEST = "1" * 64
MAP_DIGEST = "2" * 64


def provenance(label: str) -> SourceProvenance:
    return SourceProvenance(
        document_id=uuid.uuid5(uuid.NAMESPACE_URL, label),
        origin_ref=f"manual:{label}",
        revision="2026-08",
        locator=f"section:{label}",
        content_digest=SOURCE_DIGEST,
    )


def belief(
    *,
    mastery: float = 0.7,
    experience_level: str = "experienced",
    errors: tuple[str, ...] = (),
) -> LearnerBeliefSnapshot:
    identity = f"{mastery}:{experience_level}:{errors}"
    return LearnerBeliefSnapshot(
        mastery=mastery,
        confidence=0.6,
        recent_error_kinds=errors,
        hints_used=0,
        experience_level=experience_level,
        state_digest=uuid.uuid5(uuid.NAMESPACE_URL, identity).hex * 2,
    )


def ticket_contract() -> CompetencyContract:
    return CompetencyContract(
        competency_id="recover-ticket",
        version=3,
        domain="event ticket support",
        outcome="Recover the buyer ticket without sending it to an unverified address.",
        criticality="critical",
        required_fact_refs=("procedure",),
        evidence_gates=(
            EvidenceGate(
                gate_id="case-complete",
                evidence_type="case-transition-log",
                oracle_ref="oracle:ticket-state",
                source_refs=("procedure",),
            ),
        ),
        critical_errors=(
            CriticalError(
                error_id="unsafe-resend",
                description="Ticket sent to an unverified address.",
                source_refs=("procedure",),
                recovery_state="verify-address",
            ),
        ),
        mastery_policy_ref="mastery:ticket-recovery:v1",
    )


def ticket_sources() -> SourceAffordanceMap:
    return SourceAffordanceMap(
        map_id="ticket-map",
        version=2,
        competency_ref=CompetencyRef(competency_id="recover-ticket", version=3),
        source_refs={"procedure": provenance("procedure")},
        affordances=(
            SourceAffordance(
                affordance_id="case-sandbox",
                kind="operational-case",
                source_refs=("procedure",),
                supports_actions=("recover_ticket",),
                fidelity="exact",
            ),
            SourceAffordance(
                affordance_id="procedure-guide",
                kind="procedure-reference",
                source_refs=("procedure",),
                supports_actions=("follow_recovery_guide",),
                fidelity="exact",
            ),
        ),
        map_digest=MAP_DIGEST,
    )


def sql_contract() -> CompetencyContract:
    return CompetencyContract(
        competency_id="sql-filter",
        version=1,
        domain="SQL analytics",
        outcome="Return active customers using a safe parameterized query.",
        criticality="recommended",
        required_fact_refs=("schema",),
        evidence_gates=(
            EvidenceGate(
                gate_id="result-correct",
                evidence_type="query-execution-trace",
                oracle_ref="oracle:result-set",
                source_refs=("schema",),
            ),
        ),
        mastery_policy_ref="mastery:sql:v1",
    )


def sql_sources() -> SourceAffordanceMap:
    return SourceAffordanceMap(
        map_id="sql-map",
        version=1,
        competency_ref=CompetencyRef(competency_id="sql-filter", version=1),
        source_refs={"schema": provenance("schema")},
        affordances=(
            SourceAffordance(
                affordance_id="query-workspace",
                kind="executable-query",
                source_refs=("schema",),
                supports_actions=("construct_query", "debug_query"),
                fidelity="synthetic",
            ),
        ),
        map_digest=MAP_DIGEST,
    )


def test_experienced_ticket_learner_gets_action_first_episode() -> None:
    episode = build_episode_brief(ticket_contract(), ticket_sources(), belief())

    assert episode.policy_trace == {
        "strategy": "ticket-action-first",
        "reason": "sufficient-prior-experience",
        "capability_fallback": False,
    }
    assert episode.dominant_action.verb == "recover_ticket"
    assert episode.affordance_refs == ("case-sandbox",)
    assert episode.assessment_mode == "summative"
    assert episode.budget.max_content_units == 2


def test_novice_ticket_learner_gets_grounded_guide() -> None:
    episode = build_episode_brief(
        ticket_contract(),
        ticket_sources(),
        belief(mastery=0.15, experience_level="novice"),
    )

    assert episode.policy_trace["strategy"] == "ticket-guided-recovery"
    assert episode.policy_trace["reason"] == "limited-prior-experience"
    assert episode.dominant_action.verb == "follow_recovery_guide"
    assert episode.affordance_refs == ("procedure-guide",)
    assert episode.assessment_mode == "formative"
    assert episode.budget.max_content_units == 5


def test_recent_ticket_error_overrides_experience() -> None:
    episode = build_episode_brief(
        ticket_contract(),
        ticket_sources(),
        belief(errors=("unsafe-resend",)),
    )

    assert episode.policy_trace["strategy"] == "ticket-guided-recovery"
    assert episode.policy_trace["reason"] == "recent-error"


@pytest.mark.parametrize(
    ("learner", "strategy", "action"),
    [
        (belief(mastery=0.3), "sql-construct", "construct_query"),
        (
            belief(mastery=0.8, errors=("syntax-error",)),
            "sql-debug",
            "debug_query",
        ),
    ],
)
def test_sql_switches_between_construction_and_debugging(
    learner: LearnerBeliefSnapshot,
    strategy: str,
    action: str,
) -> None:
    episode = build_episode_brief(sql_contract(), sql_sources(), learner)

    assert episode.policy_trace["strategy"] == strategy
    assert episode.dominant_action.verb == action
    assert episode.affordance_refs == ("query-workspace",)


def test_policy_is_deterministic_and_belief_sensitive() -> None:
    learner = belief()
    first = build_episode_brief(ticket_contract(), ticket_sources(), learner)
    second = build_episode_brief(ticket_contract(), ticket_sources(), learner)
    changed = build_episode_brief(
        ticket_contract(), ticket_sources(), belief(errors=("unsafe-resend",))
    )

    assert first == second
    assert first.episode_id == second.episode_id
    assert changed.episode_id != first.episode_id


def test_episode_is_fully_grounded_and_has_safety_continuation() -> None:
    episode = build_episode_brief(ticket_contract(), ticket_sources(), belief())

    assert episode.source_refs == ("procedure",)
    assert episode.evidence_gate_refs == ("case-complete",)
    assert episode.critical_error_refs == ("unsafe-resend",)
    recovery = next(
        item
        for item in episode.continuation_conditions
        if item.kind == "critical_error_detected"
    )
    assert recovery.destination_state == "verify-address"
    assert sum(item.is_default for item in episode.continuation_conditions) == 1


def test_policy_falls_back_to_declared_capability_without_inventing_one() -> None:
    source_map = ticket_sources().model_copy(
        update={
            "affordances": (
                SourceAffordance(
                    affordance_id="available-task",
                    kind="grounded-task",
                    source_refs=("procedure",),
                    supports_actions=("perform_declared_task",),
                    fidelity="derived",
                ),
            )
        }
    )
    episode = build_episode_brief(ticket_contract(), source_map, belief())

    assert episode.dominant_action.verb == "perform_declared_task"
    assert episode.policy_trace["capability_fallback"] is True


def test_cross_validation_is_mandatory() -> None:
    mismatched = ticket_sources().model_copy(
        update={
            "competency_ref": CompetencyRef(
                competency_id="different-competency",
                version=1,
            )
        }
    )

    with pytest.raises(ValueError, match="same contract version"):
        build_episode_brief(ticket_contract(), mismatched, belief())


def test_policy_output_contains_no_render_or_provider_decisions() -> None:
    payload = build_episode_brief(sql_contract(), sql_sources(), belief()).model_dump_json()

    for forbidden in (
        '"component"',
        '"provider"',
        '"slot"',
        '"lead"',
        '"concept"',
        '"practice"',
        '"screen"',
    ):
        assert forbidden not in payload


def test_custom_domain_strategy_is_registered_without_policy_changes() -> None:
    competency = CompetencyContract(
        competency_id="inspect-bearing",
        version=1,
        domain="industrial maintenance",
        outcome="Identify bearing wear before restarting the machine.",
        criticality="recommended",
        required_fact_refs=("maintenance-manual",),
        evidence_gates=(
            EvidenceGate(
                gate_id="inspection-recorded",
                evidence_type="inspection-trace",
                oracle_ref="oracle:bearing-inspection",
                source_refs=("maintenance-manual",),
            ),
        ),
        mastery_policy_ref="mastery:maintenance:v1",
    )
    source_map = SourceAffordanceMap(
        map_id="maintenance-map",
        version=1,
        competency_ref=CompetencyRef(competency_id="inspect-bearing", version=1),
        source_refs={"maintenance-manual": provenance("maintenance-manual")},
        affordances=(
            SourceAffordance(
                affordance_id="bearing-inspection",
                kind="equipment-inspection",
                source_refs=("maintenance-manual",),
                supports_actions=("inspect_bearing",),
                fidelity="exact",
            ),
        ),
        map_digest=MAP_DIGEST,
    )
    maintenance = EpisodeStrategy(
        name="maintenance-inspection",
        matcher=lambda contract, _belief: "maintenance" in contract.domain.casefold(),
        reason="equipment-safety",
        preferred_actions=("inspect_bearing",),
        action_terms=("inspect",),
        instruction="Inspect the grounded equipment state and record the evidence.",
        budget=EpisodeBudget(
            max_content_units=2,
            max_interaction_steps=6,
            max_words=180,
            latency_budget_ms=1500,
        ),
    )

    episode = build_episode_brief(
        competency,
        source_map,
        belief(mastery=0.5),
        strategies=(maintenance,),
    )

    assert episode.policy_trace["strategy"] == "maintenance-inspection"
    assert episode.dominant_action.verb == "inspect_bearing"
