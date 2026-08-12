import pytest

from src.agents.runtime.selection_eval import (
    EfficiencyMetrics,
    ExpectedOutcome,
    GateCode,
    SelectionExpectations,
    SelectionObservation,
    WeightedRequirement,
    evaluate_selection,
)


def req(requirement_id: str, weight: float = 1.0) -> WeightedRequirement:
    return WeightedRequirement(requirement_id, weight)


def expectations(**overrides) -> SelectionExpectations:
    values = {
        "scenario_id": "complaint:novice-visual",
        "critical_facts": (req("escalate_health"), req("do_not_promise")),
        "required_affordances": (req("inspect"), req("choose", 2), req("review")),
        "required_evidence": (req("decision_submitted"), req("feedback_seen")),
        "applicable_preferences": (req("visual_structure"), req("graduated_hints")),
        "required_accessibility": (req("keyboard"),),
        "desired_accessibility": (req("reduced_motion"),),
        "target_depth": 3,
    }
    values.update(overrides)
    return SelectionExpectations(**values)


def observation(**overrides) -> SelectionObservation:
    values = {
        "facts_covered": frozenset({"escalate_health", "do_not_promise"}),
        "affordances": frozenset({"inspect", "choose", "review"}),
        "evidence_events": frozenset({"decision_submitted", "feedback_seen"}),
        "preferences_satisfied": frozenset({"visual_structure", "graduated_hints"}),
        "accessibility_capabilities": frozenset({"keyboard", "reduced_motion"}),
        "depth": 3,
        "representation": "interactive",
        "support_policy": "novice:hints",
    }
    values.update(overrides)
    return SelectionObservation(**values)


def test_complete_experience_passes_with_capability_based_signature() -> None:
    result = evaluate_selection(expectations(), observation())

    assert result.gate_passed is True
    assert result.gate_failures == ()
    assert result.quality_score == 100.0
    assert result.semantic_signature is not None
    assert result.semantic_signature.as_key() == (
        ("choose", "inspect", "review"),
        ("decision_submitted", "feedback_seen"),
        "interactive",
        "novice:hints",
        3,
    )


def test_gates_cannot_be_compensated_by_perfect_capabilities() -> None:
    result = evaluate_selection(
        expectations(),
        observation(
            facts_covered=frozenset({"do_not_promise"}),
            facts_contradicted=frozenset({"escalate_health"}),
            unsupported_critical_claims=("always refund in cash",),
        ),
    )

    assert result.gate_passed is False
    assert result.quality_score is None
    assert {failure.code for failure in result.gate_failures} == {
        GateCode.CRITICAL_FACT_MISSING,
        GateCode.CRITICAL_FACT_CONTRADICTED,
        GateCode.UNSUPPORTED_CRITICAL_CLAIM,
    }


def test_required_accessibility_is_a_gate_and_desired_accessibility_is_coverage() -> None:
    blocked = evaluate_selection(
        expectations(), observation(accessibility_capabilities=frozenset())
    )
    partial = evaluate_selection(
        expectations(), observation(accessibility_capabilities=frozenset({"keyboard"}))
    )

    assert blocked.gate_passed is False
    assert blocked.gate_failures[-1].code is GateCode.ACCESSIBILITY_REQUIRED_MISSING
    assert partial.gate_passed is True
    assert partial.dimensions is not None
    assert partial.dimensions.accessibility_coverage == 0.5


def test_weighted_coverage_rewards_required_actions_not_raw_action_count() -> None:
    result = evaluate_selection(
        expectations(),
        observation(
            affordances=frozenset({"inspect", "review", "decorate", "animate", "share"}),
            evidence_events=frozenset({"feedback_seen"}),
        ),
    )

    assert result.dimensions is not None
    assert result.dimensions.affordance_coverage == 0.5
    assert result.dimensions.evidence_coverage == 0.5
    # Five observed actions do not beat the missing, double-weighted `choose` action.
    assert result.quality_score == 70.0


def test_irrelevant_preference_is_excluded_instead_of_awarding_free_points() -> None:
    no_preference = expectations(applicable_preferences=())
    left = evaluate_selection(no_preference, observation(preferences_satisfied=frozenset()))
    right = evaluate_selection(
        no_preference,
        observation(preferences_satisfied=frozenset({"visual_structure", "anything"})),
    )

    assert left.dimensions is not None
    assert left.dimensions.preference_coverage is None
    assert left.quality_score == right.quality_score == 100.0


def test_dimensions_without_declared_requirements_are_not_free_points_or_penalties() -> None:
    sparse = expectations(
        required_affordances=(),
        required_evidence=(),
        applicable_preferences=(),
        required_accessibility=(),
        desired_accessibility=(),
    )
    result = evaluate_selection(sparse, observation())

    assert result.dimensions is not None
    assert result.dimensions.affordance_coverage is None
    assert result.dimensions.evidence_coverage is None
    assert result.dimensions.accessibility_coverage is None
    assert result.quality_score == 100.0


def test_depth_scores_distance_from_target_and_does_not_reward_more_depth() -> None:
    too_shallow = evaluate_selection(expectations(), observation(depth=2))
    too_deep = evaluate_selection(expectations(), observation(depth=4))

    assert too_shallow.dimensions is not None
    assert too_deep.dimensions is not None
    assert too_shallow.dimensions.depth_fit == too_deep.dimensions.depth_fit == 0.75
    assert too_shallow.quality_score == too_deep.quality_score


def test_efficiency_is_reported_but_never_changes_quality() -> None:
    fast = evaluate_selection(
        expectations(), observation(efficiency=EfficiencyMetrics(latency_ms=100, tokens_out=20))
    )
    slow = evaluate_selection(
        expectations(),
        observation(efficiency=EfficiencyMetrics(latency_ms=90_000, tokens_out=20_000)),
    )

    assert fast.quality_score == slow.quality_score == 100.0
    assert fast.efficiency != slow.efficiency


def test_honest_expected_decline_passes_without_inventing_a_quality_score() -> None:
    result = evaluate_selection(
        expectations(expected_outcome=ExpectedOutcome.DECLINE),
        SelectionObservation(declined=True, decline_reason="missing_rules"),
    )

    assert result.gate_passed is True
    assert result.quality_score is None
    assert result.semantic_signature is None


def test_unexpected_decline_and_expected_decline_but_produced_are_mismatches() -> None:
    unexpected = evaluate_selection(
        expectations(), SelectionObservation(declined=True, decline_reason="gave_up")
    )
    dishonest = evaluate_selection(
        expectations(expected_outcome=ExpectedOutcome.DECLINE), observation()
    )

    assert unexpected.gate_failures[0].code is GateCode.OUTCOME_MISMATCH
    assert dishonest.gate_failures[0].code is GateCode.OUTCOME_MISMATCH
    assert dishonest.quality_score is None


def test_contract_rejects_invalid_depth_weights_duplicates_and_reasonless_decline() -> None:
    with pytest.raises(ValueError, match="target_depth"):
        expectations(target_depth=5)
    with pytest.raises(ValueError, match="positive"):
        req("x", 0)
    with pytest.raises(ValueError, match="duplicate"):
        expectations(required_affordances=(req("choose"), req("choose")))
    with pytest.raises(ValueError, match="reason"):
        SelectionObservation(declined=True)
