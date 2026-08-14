"""Provider-neutral episode contracts for unlike enterprise learning domains."""

import uuid

import pytest
from pydantic import ValidationError

from src.schemas.episode_contracts import (
    CompetencyContract,
    CompetencyRef,
    ContinuationCondition,
    CriticalError,
    DominantAction,
    EpisodeBrief,
    EpisodeBudget,
    EvidenceGate,
    LearnerBeliefSnapshot,
    SourceAffordance,
    SourceAffordanceMap,
    SourceProvenance,
    validate_episode_contracts,
)

ZERO_DIGEST = "0" * 64
ONE_DIGEST = "1" * 64
DOCUMENT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


def provenance(locator: str) -> SourceProvenance:
    return SourceProvenance(
        document_id=DOCUMENT_ID,
        origin_ref="manual:ticket-recovery",
        revision="2026",
        locator=locator,
        content_digest=ZERO_DIGEST,
    )


def ticket_competency(**overrides) -> CompetencyContract:
    values = {
        "competency_id": "recover-ticket",
        "version": 3,
        "domain": "ticket-operations",
        "outcome": "Recover the buyer's ticket without bypassing identity checks.",
        "criticality": "critical",
        "required_fact_refs": ("procedure", "wrong-email"),
        "evidence_gates": (
            EvidenceGate(
                gate_id="complete-case",
                evidence_type="operational_case_result",
                oracle_ref="ticket-recovery-oracle/1",
                source_refs=("procedure", "wrong-email"),
                minimum_score=1.0,
            ),
        ),
        "critical_errors": (
            CriticalError(
                error_id="resend-to-wrong-email",
                description="Do not resend automatically to an incorrect address.",
                source_refs=("wrong-email",),
                recovery_state="verify-address",
            ),
        ),
        "mastery_policy_ref": "critical-operation/1",
    }
    values.update(overrides)
    return CompetencyContract(**values)


def ticket_sources(**overrides) -> SourceAffordanceMap:
    values = {
        "map_id": "ticket-recovery-grounding",
        "version": 2,
        "competency_ref": CompetencyRef(competency_id="recover-ticket", version=3),
        "source_refs": {
            "procedure": provenance("page:2#steps"),
            "wrong-email": provenance("page:1#critical-note"),
        },
        "affordances": (
            SourceAffordance(
                affordance_id="recovery-case",
                kind="operational_case",
                source_refs=("procedure", "wrong-email"),
                supports_actions=("recover_ticket", "inspect_state"),
                fidelity="derived",
                runtime_requirements={"identity_check": True},
            ),
        ),
        "map_digest": ONE_DIGEST,
    }
    values.update(overrides)
    return SourceAffordanceMap(**values)


def belief() -> LearnerBeliefSnapshot:
    return LearnerBeliefSnapshot(
        mastery=0.35,
        confidence=0.6,
        recent_error_kinds=("wrong-platform",),
        hints_used=1,
        experience_level="novice",
        state_digest=ZERO_DIGEST,
    )


def budget(**overrides) -> EpisodeBudget:
    values = {
        "max_content_units": 5,
        "max_interaction_steps": 8,
        "max_words": 240,
        "max_media_seconds": 90,
        "latency_budget_ms": 2500,
    }
    values.update(overrides)
    return EpisodeBudget(**values)


def ticket_episode(**overrides) -> EpisodeBrief:
    values = {
        "episode_id": uuid.uuid4(),
        "version": 1,
        "competency_ref": CompetencyRef(competency_id="recover-ticket", version=3),
        "belief_snapshot": belief(),
        "grounding_map_id": "ticket-recovery-grounding",
        "grounding_map_version": 2,
        "grounding_digest": ONE_DIGEST,
        "source_refs": ("procedure", "wrong-email"),
        "affordance_refs": ("recovery-case",),
        "dominant_action": DominantAction(
            action_id="resolve-case",
            verb="recover_ticket",
            target="Buyer case in the selected ticket platform",
            submission_kind="case_transition_log",
            instructions="Recover the ticket and stop if identity cannot be verified.",
            constraints={"preserve_order": True},
        ),
        "assessment_mode": "summative",
        "evidence_gate_refs": ("complete-case",),
        "critical_error_refs": ("resend-to-wrong-email",),
        "budget": budget(),
        "continuation_conditions": (
            ContinuationCondition(
                condition_id="case-passed",
                kind="evidence_satisfied",
                destination_state="competency-complete",
                evidence_gate_refs=("complete-case",),
                priority=10,
            ),
            ContinuationCondition(
                condition_id="unsafe-resend",
                kind="critical_error_detected",
                destination_state="verify-address",
                critical_error_refs=("resend-to-wrong-email",),
                priority=20,
            ),
            ContinuationCondition(
                condition_id="fallback",
                kind="always",
                destination_state="guided-recovery",
                priority=100,
                is_default=True,
            ),
        ),
        "policy_trace": {"strategy": "case-first", "reason": "declared-novice"},
    }
    values.update(overrides)
    return EpisodeBrief(**values)


def test_ticket_operation_contracts_are_valid_without_screen_formula() -> None:
    competency = ticket_competency()
    sources = ticket_sources()
    episode = ticket_episode()

    validate_episode_contracts(competency, sources, episode)
    assert episode.dominant_action.verb == "recover_ticket"
    assert episode.budget.max_primary_actions == 1
    forbidden = {"lead", "concept", "practice", "component_id", "provider"}
    assert forbidden.isdisjoint(EpisodeBrief.model_fields)


def test_sql_uses_an_executable_affordance_not_a_ticket_screen_shape() -> None:
    competency = CompetencyContract(
        competency_id="aggregate-orders",
        version=1,
        domain="sql",
        outcome="Write a grouped query that returns revenue per customer.",
        criticality="recommended",
        required_fact_refs=("schema", "expected-semantics"),
        evidence_gates=(
            EvidenceGate(
                gate_id="hidden-tests",
                evidence_type="executable_result",
                oracle_ref="sql-test-suite/7",
                source_refs=("schema", "expected-semantics"),
                minimum_score=1.0,
            ),
        ),
        mastery_policy_ref="sql-execution/1",
    )
    sources = SourceAffordanceMap(
        map_id="sql-orders",
        version=1,
        competency_ref=CompetencyRef(competency_id="aggregate-orders", version=1),
        source_refs={
            "schema": provenance("dataset:orders#schema"),
            "expected-semantics": provenance("lesson:grouping#outcome"),
        },
        affordances=(
            SourceAffordance(
                affordance_id="query-sandbox",
                kind="executable_dataset",
                source_refs=("schema", "expected-semantics"),
                supports_actions=("execute_query", "inspect_result"),
                fidelity="exact",
                runtime_requirements={"network": False, "read_only": True},
            ),
        ),
        map_digest=ZERO_DIGEST,
    )
    episode = ticket_episode(
        competency_ref=CompetencyRef(competency_id="aggregate-orders", version=1),
        grounding_map_id="sql-orders",
        grounding_map_version=1,
        grounding_digest=ZERO_DIGEST,
        source_refs=("schema", "expected-semantics"),
        affordance_refs=("query-sandbox",),
        dominant_action=DominantAction(
            action_id="run-query",
            verb="execute_query",
            target="Frozen orders dataset",
            submission_kind="sql_text",
            instructions="Run a query and inspect the grouped result.",
            constraints={"read_only": True},
        ),
        evidence_gate_refs=("hidden-tests",),
        critical_error_refs=(),
        continuation_conditions=(
            ContinuationCondition(
                condition_id="tests-pass",
                kind="evidence_satisfied",
                destination_state="competency-complete",
                evidence_gate_refs=("hidden-tests",),
                priority=10,
            ),
            ContinuationCondition(
                condition_id="retry",
                kind="always",
                destination_state="debug-query",
                priority=100,
                is_default=True,
            ),
        ),
    )

    validate_episode_contracts(competency, sources, episode)
    assert episode.dominant_action.submission_kind == "sql_text"


def test_contracts_are_closed_frozen_and_versioned() -> None:
    episode = ticket_episode()
    with pytest.raises(ValidationError, match="frozen"):
        episode.assessment_mode = "none"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ticket_episode(lead="Read this first")
    with pytest.raises(ValidationError, match="Input should be 1"):
        ticket_episode(schema_version=2)


@pytest.mark.parametrize(
    "metadata",
    [
        {"provider": "didact"},
        {"nested": {"component_id": "quiz"}},
        {"slots": ["lead", "practice"]},
    ],
)
def test_extensible_metadata_cannot_smuggle_render_architecture(metadata: dict) -> None:
    with pytest.raises(ValidationError, match="render-specific"):
        ticket_episode(policy_trace=metadata)


def test_critical_competency_requires_explicit_blocking_errors() -> None:
    with pytest.raises(ValidationError, match="needs explicit critical errors"):
        ticket_competency(critical_errors=())
    non_blocking = CriticalError(
        error_id="unsafe",
        description="Unsafe action",
        source_refs=("wrong-email",),
        blocking=False,
        recovery_state="recover",
    )
    with pytest.raises(ValidationError, match="must block progression"):
        ticket_competency(critical_errors=(non_blocking,))


def test_required_evidence_and_ids_are_validated() -> None:
    optional = EvidenceGate(
        gate_id="optional",
        evidence_type="reflection",
        oracle_ref="reflection/1",
        source_refs=("procedure",),
        required=False,
    )
    with pytest.raises(ValidationError, match="at least one evidence gate"):
        ticket_competency(evidence_gates=(optional,))
    duplicate = ticket_competency().evidence_gates[0]
    with pytest.raises(ValidationError, match="gate ids must be unique"):
        ticket_competency(evidence_gates=(duplicate, duplicate))


def test_source_provenance_and_affordance_references_are_closed() -> None:
    with pytest.raises(ValidationError, match="String should match pattern"):
        SourceProvenance(
            document_id=DOCUMENT_ID,
            origin_ref="manual",
            revision="1",
            locator="page:1",
            content_digest="weak",
        )
    bad_affordance = SourceAffordance(
        affordance_id="bad",
        kind="screenshot",
        source_refs=("missing",),
        supports_actions=("inspect_state",),
        fidelity="exact",
    )
    with pytest.raises(ValidationError, match="unknown source refs"):
        ticket_sources(affordances=(bad_affordance,))
    with pytest.raises(ValidationError, match="opaque identifiers"):
        ticket_sources(source_refs={"bad ref": provenance("page:1")})


def test_episode_flow_needs_one_default_and_complete_gate_coverage() -> None:
    no_default = tuple(
        condition.model_copy(update={"is_default": False})
        for condition in ticket_episode().continuation_conditions
    )
    with pytest.raises(ValidationError, match="exactly one default"):
        ticket_episode(continuation_conditions=no_default)

    missing_evidence_branch = tuple(
        condition
        for condition in ticket_episode().continuation_conditions
        if condition.kind != "evidence_satisfied"
    )
    with pytest.raises(ValidationError, match="evidence gate needs a continuation"):
        ticket_episode(continuation_conditions=missing_evidence_branch)

    missing_recovery = tuple(
        condition
        for condition in ticket_episode().continuation_conditions
        if condition.kind != "critical_error_detected"
    )
    with pytest.raises(ValidationError, match="critical error needs a recovery"):
        ticket_episode(continuation_conditions=missing_recovery)


def test_unassessed_episode_cannot_claim_or_branch_on_evidence() -> None:
    with pytest.raises(ValidationError, match="unassessed episode"):
        ticket_episode(assessment_mode="none")


def test_budget_enforces_one_dominant_action_and_real_bounds() -> None:
    with pytest.raises(ValidationError, match="Input should be 1"):
        budget(max_primary_actions=2)
    with pytest.raises(ValidationError, match="greater than or equal to 50"):
        budget(latency_budget_ms=20)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"grounding_map_version": 99}, "pin the exact source"),
        ({"grounding_digest": ZERO_DIGEST}, "pin the exact source"),
        ({"source_refs": ("procedure",)}, "pin every source"),
        ({"affordance_refs": ("unknown",)}, "unknown affordance"),
        (
            {
                "dominant_action": DominantAction(
                    action_id="wrong",
                    verb="execute_query",
                    target="ticket",
                    submission_kind="text",
                    instructions="Run SQL.",
                )
            },
            "unsupported",
        ),
    ],
)
def test_cross_contract_validation_rejects_drift(mutation: dict, message: str) -> None:
    episode = ticket_episode(**mutation)
    with pytest.raises(ValueError, match=message):
        validate_episode_contracts(ticket_competency(), ticket_sources(), episode)


def test_cross_contract_validation_rejects_unknown_gate_after_local_validation() -> None:
    conditions = tuple(
        condition
        for condition in ticket_episode().continuation_conditions
        if condition.kind != "evidence_satisfied"
    ) + (
        ContinuationCondition(
            condition_id="unknown-passed",
            kind="evidence_satisfied",
            destination_state="competency-complete",
            evidence_gate_refs=("unknown",),
            priority=10,
        ),
    )
    episode = ticket_episode(
        evidence_gate_refs=("unknown",), continuation_conditions=conditions
    )
    with pytest.raises(ValueError, match="unknown evidence"):
        validate_episode_contracts(ticket_competency(), ticket_sources(), episode)


def test_cross_contract_validation_rejects_unknown_error_after_local_validation() -> None:
    conditions = tuple(
        condition
        for condition in ticket_episode().continuation_conditions
        if condition.kind != "critical_error_detected"
    ) + (
        ContinuationCondition(
            condition_id="unknown-recovery",
            kind="critical_error_detected",
            destination_state="safe-recovery",
            critical_error_refs=("unknown",),
            priority=20,
        ),
    )
    episode = ticket_episode(
        critical_error_refs=("unknown",), continuation_conditions=conditions
    )
    with pytest.raises(ValueError, match="unknown critical"):
        validate_episode_contracts(ticket_competency(), ticket_sources(), episode)


def test_cross_contract_validation_rejects_unknown_competency_sources() -> None:
    competency = ticket_competency(required_fact_refs=("procedure", "missing"))
    with pytest.raises(ValueError, match="competency references unknown sources"):
        validate_episode_contracts(competency, ticket_sources(), ticket_episode())


def test_continuation_condition_payload_matches_its_kind() -> None:
    with pytest.raises(ValidationError, match="needs evidence_gate_refs"):
        ContinuationCondition(
            condition_id="bad",
            kind="evidence_satisfied",
            destination_state="next",
            priority=1,
        )
    with pytest.raises(ValidationError, match="cannot carry gate refs"):
        ContinuationCondition(
            condition_id="bad-default",
            kind="always",
            destination_state="next",
            evidence_gate_refs=("gate",),
            priority=1,
            is_default=True,
        )
