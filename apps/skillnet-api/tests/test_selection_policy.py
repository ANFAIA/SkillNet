from __future__ import annotations

import pytest

from src.personalization.selection_policy import (
    CONTRACT_VERSION,
    ProgressiveStage,
    SelectionExecution,
    SelectionCandidate,
    SelectionPolicyError,
    SelectionRequest,
    SelectionStrategy,
    live_cache_fragment,
    runtime_execution,
    select,
)


CANDIDATES = (
    SelectionCandidate("a1", "content"),
    SelectionCandidate("a2", "content"),
    SelectionCandidate("a3", "content"),
    SelectionCandidate("b1", "assessment"),
    SelectionCandidate("c1", "media"),
    SelectionCandidate("d1", "simulation"),
    SelectionCandidate("e1", "deterministic"),
    SelectionCandidate("f1", "content"),
    SelectionCandidate("g1", "assessment"),
)


def test_strategy_ids_are_explicitly_versioned() -> None:
    assert {item.value for item in SelectionStrategy} == {
        "top5/v1",
        "portfolio-balanced-5/v1",
        "portfolio-exploratory-8/v1",
        "progressive-3-5-catalog/v1",
        "dual-agent/v1",
        "conditional-specialist/v1",
        "full-catalog-control/v1",
    }


def test_deterministic_policies_execute_different_search_spaces_with_complete_traces() -> None:
    top5 = select(SelectionRequest(strategy=SelectionStrategy.TOP5, candidates=CANDIDATES))
    balanced = select(
        SelectionRequest(
            strategy=SelectionStrategy.PORTFOLIO_BALANCED_5,
            candidates=CANDIDATES,
        )
    )
    exploratory = select(
        SelectionRequest(
            strategy=SelectionStrategy.PORTFOLIO_EXPLORATORY_8,
            candidates=CANDIDATES,
        )
    )
    full = select(
        SelectionRequest(
            strategy=SelectionStrategy.FULL_CATALOG_CONTROL,
            candidates=CANDIDATES,
        )
    )

    assert top5.selected_ids == ("a1", "a2", "a3", "b1", "c1")
    assert balanced.selected_ids == ("a1", "a2", "b1", "c1", "d1")
    assert exploratory.selected_ids == ("a1", "b1", "c1", "d1", "e1", "a2", "a3", "f1")
    assert full.selected_ids == tuple(item.candidate_id for item in CANDIDATES)
    assert len({top5.selected_ids, balanced.selected_ids, exploratory.selected_ids, full.selected_ids}) == 4
    for result in (top5, balanced, exploratory, full):
        assert result.trace.contract_version == CONTRACT_VERSION
        assert result.trace.requested_strategy is result.trace.executed_strategy
        assert result.trace.selected_ids == result.selected_ids
        assert result.trace.considered_ids == tuple(item.candidate_id for item in CANDIDATES)
        assert result.trace.decision_codes


def test_progressive_dual_and_specialist_inputs_are_explicit() -> None:
    progressive = select(
        SelectionRequest(
            strategy=SelectionStrategy.PROGRESSIVE_3_5_CATALOG,
            candidates=CANDIDATES,
            progressive_stage=ProgressiveStage.TOP5,
        )
    )
    dual = select(
        SelectionRequest(
            strategy=SelectionStrategy.DUAL_AGENT,
            candidates=CANDIDATES,
            secondary_ranking=("e1", "d1", "c1", "b1", "a1"),
        )
    )
    specialist = select(
        SelectionRequest(
            strategy=SelectionStrategy.CONDITIONAL_SPECIALIST,
            candidates=CANDIDATES,
            activate_specialist=True,
            specialist_ranking=("d1", "c1"),
        )
    )

    assert progressive.selected_ids == ("a1", "a2", "a3", "b1", "c1")
    assert progressive.trace.stage == "top5"
    assert dual.selected_ids == ("a1", "e1", "a2", "d1", "a3")
    assert dual.trace.stage == "dual-merge"
    assert specialist.selected_ids == ("d1", "c1", "a1", "a2", "a3")
    assert specialist.trace.stage == "specialist"


def test_unknown_and_incomplete_strategies_fail_closed() -> None:
    with pytest.raises(SelectionPolicyError, match="unknown selection strategy"):
        SelectionStrategy.parse("decorative-label")
    with pytest.raises(SelectionPolicyError, match="secondary_ranking"):
        select(SelectionRequest(strategy=SelectionStrategy.DUAL_AGENT, candidates=CANDIDATES))
    with pytest.raises(SelectionPolicyError, match="specialist_ranking"):
        select(
            SelectionRequest(
                strategy=SelectionStrategy.CONDITIONAL_SPECIALIST,
                candidates=CANDIDATES,
                activate_specialist=True,
            )
        )


def test_runtime_capabilities_keep_second_ranking_policies_out_of_live() -> None:
    assert (
        runtime_execution(SelectionExecution.LIVE, SelectionStrategy.TOP5)
        is SelectionExecution.LIVE
    )
    assert (
        runtime_execution(SelectionExecution.LIVE, SelectionStrategy.DUAL_AGENT)
        is SelectionExecution.SHADOW
    )
    assert (
        runtime_execution(
            SelectionExecution.LIVE, SelectionStrategy.CONDITIONAL_SPECIALIST
        )
        is SelectionExecution.SHADOW
    )
    assert (
        live_cache_fragment(SelectionExecution.LIVE, SelectionStrategy.TOP5)
        == "selection-policy/1:top5/v1"
    )
    assert (
        live_cache_fragment(SelectionExecution.LIVE, SelectionStrategy.DUAL_AGENT)
        == ""
    )
    with pytest.raises(SelectionPolicyError, match="unknown progressive stage"):
        select(
            SelectionRequest(
                strategy=SelectionStrategy.PROGRESSIVE_3_5_CATALOG,
                candidates=CANDIDATES,
                progressive_stage="guessed",  # type: ignore[arg-type]
            )
        )
