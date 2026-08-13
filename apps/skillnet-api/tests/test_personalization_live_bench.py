from __future__ import annotations

from dataclasses import asdict

import pytest

from scripts import personalization_live_bench as bench
from scripts import quality_bench as quality
from src.personalization.selection_policy import SelectionStrategy


def _run(
    *,
    profile: str,
    candidate: str,
    observable: str | None = None,
    action_type: str = "DidactActivity",
    callout: str | None = None,
    outcome: str = "first_pass",
    activity_status: str = "not_observed",
    authored_activity: dict | None = None,
) -> dict:
    components = [{"type": action_type, "props": {"variant": observable}}]
    if callout is not None:
        components.append({"type": "Callout", "props": {"text": callout}})
    result = quality.RunResult(
        encargo="same-node",
        repeat=1,
        arm="raw",
        context="raw_source",
        outcome=outcome,
        ui_format="exercise",
        tier="fast",
        model="fixture/bench",
        decide_called=True,
        attempts=1,
        seconds=0.1,
        tokens_in=None,
        tokens_out=None,
        cost_usd=None,
        tokens_measured=False,
        render_status="ready",
        steps=list(quality._GRAPH_NODE_NAMES),
        cache_key="key",
        source_digest="same-source",
        block_types=[item["type"] for item in components],
        ui_spec={"components": components},
        plan_trace={
            "projection": {"profile": profile},
            "shadow": {"component_candidates": [{"component_id": candidate}]},
        },
        activity_authoring_status=activity_status,
        authored_activity=authored_activity,
    )
    signature = bench.hashlib.sha256(
        bench.json.dumps(bench._signature(result), sort_keys=True).encode()
    ).hexdigest()
    superficial_signature = bench.hashlib.sha256(
        bench._superficial_signature(result).encode()
    ).hexdigest()
    return {
        "case": "same-node",
        "profile": profile,
        "repeat": 1,
        "objective": "practice",
        "source": "source",
        "run": asdict(result),
        "didact_candidates": list(bench._didact_ids(result)),
        "semantic_signature": signature,
        "superficial_signature": superficial_signature,
    }


def test_matrix_profiles_are_real_counterfactuals() -> None:
    base = quality.CORPUS[0]
    cases = [bench._case(base, profile) for profile in bench.PROFILES]

    assert len({case.source_text for case in cases}) == 1
    assert len({case.outcome for case in cases}) == 1
    assert len({case.experience_level for case in cases}) == 3
    assert len({case.preset for case in cases}) == 3


def test_strategy_argument_is_validated_and_preflight_is_honest() -> None:
    args = bench.parser().parse_args(["--strategy", "portfolio-balanced-5/v1", "--plan"])
    preflight = bench._selection_preflight(args.strategy)

    assert args.strategy is SelectionStrategy.PORTFOLIO_BALANCED_5
    assert preflight == {
        "requested_strategy": "portfolio-balanced-5/v1",
        "requested_execution": "live",
        "effective_execution": "live",
        "executed_strategy": "portfolio-balanced-5/v1",
        "selection_contract_connected": True,
        "claim_boundary": (
            "Observed execution is read from each runtime plan trace. Strategies requiring "
            "an independent ranking remain shadow-only."
        ),
    }


def test_dual_agent_preflight_does_not_claim_live_execution() -> None:
    preflight = bench._selection_preflight(SelectionStrategy.DUAL_AGENT)

    assert preflight["requested_execution"] == "live"
    assert preflight["effective_execution"] == "shadow"
    assert preflight["executed_strategy"] is None


def test_selection_observation_reads_actual_runtime_trace() -> None:
    result = quality.RunResult(
        encargo="same-node",
        repeat=1,
        arm="raw",
        context="raw_source",
        outcome="first_pass",
        ui_format="exercise",
        tier="fast",
        model="fixture/bench",
        decide_called=True,
        attempts=1,
        seconds=0.1,
        tokens_in=None,
        tokens_out=None,
        cost_usd=None,
        tokens_measured=False,
        render_status="ready",
        steps=[],
        cache_key="key",
        source_digest="digest",
        block_types=[],
        plan_trace={
            "selection": {
                "requested_strategy": "progressive-3-5-catalog/v1",
                "requested_execution": "live",
                "effective_execution": "live",
                "executed_strategy": "progressive-3-5-catalog/v1",
                "status": "executed",
            }
        },
    )

    assert bench._selection_observation(result) == {
        "requested_strategy": "progressive-3-5-catalog/v1",
        "requested_execution": "live",
        "effective_execution": "live",
        "executed_strategy": "progressive-3-5-catalog/v1",
        "status": "executed",
    }


def test_unknown_strategy_argument_is_rejected() -> None:
    with pytest.raises(SystemExit):
        bench.parser().parse_args(["--strategy", "decorative-label"])


def test_audit_accounts_for_all_34_types_and_detects_observable_change() -> None:
    rows = [
        _run(
            profile="novice_guided",
            candidate="didact.flashcard",
            action_type="Flashcard",
        ),
        _run(
            profile="practitioner",
            candidate="didact.timeline-steps",
            action_type="DragOrder",
        ),
        _run(
            profile="expert_fast",
            candidate="didact.data-explorer",
            action_type="QuizItem",
        ),
    ]

    audit = bench._audit(rows)

    assert audit["metrics"]["didact_inventory_count"] == 34
    assert len(audit["didact_inventory"]) == 34
    assert audit["gates"]["catalog_exactly_34"] is True
    assert audit["gates"]["useful_counterfactual_change_gte_0_50"] is True


def test_profile_input_change_with_identical_output_has_zero_causal_change() -> None:
    rows = [
        _run(profile="novice_guided", candidate="didact.flashcard", observable="same"),
        _run(profile="expert_fast", candidate="didact.data-explorer", observable="same"),
    ]

    audit = bench._audit(rows)

    assert audit["metrics"]["useful_counterfactual_causal_change_rate"] == 0.0
    assert audit["gates"]["useful_counterfactual_change_gte_0_50"] is False


def test_callout_only_change_is_superficial_not_useful() -> None:
    rows = [
        _run(
            profile="novice_guided",
            candidate="didact.flashcard",
            action_type="DragOrder",
            callout="Ayuda para principiantes",
        ),
        _run(
            profile="expert_fast",
            candidate="didact.flashcard",
            action_type="DragOrder",
            callout="Resumen para expertos",
        ),
    ]

    audit = bench._audit(rows)

    assert audit["metrics"]["useful_counterfactual_causal_change_rate"] == 0.0
    assert audit["metrics"]["superficial_change_rate"] == 1.0


def test_fallback_rate_is_a_promotion_gate() -> None:
    rows = [
        _run(profile="novice_guided", candidate="didact.flashcard"),
        _run(profile="expert_fast", candidate="didact.flashcard", outcome="fallback"),
    ]

    audit = bench._audit(rows)

    assert audit["metrics"]["fallback_rate"] == 0.5
    assert audit["gates"]["fallback_rate_lte_0_10"] is False


def test_requested_activity_materialization_has_a_minimum_gate() -> None:
    rows = [
        _run(
            profile="novice_guided",
            candidate="didact.data-explorer",
            activity_status="declined:ValidationError",
        ),
        _run(
            profile="expert_fast",
            candidate="didact.data-explorer",
            activity_status="ready",
            authored_activity={
                "component_id": "didact.data-explorer",
                "public_definition": {"definition": {"id": "data-1"}},
            },
        ),
    ]

    audit = bench._audit(rows)

    assert audit["metrics"]["activity_materialization_rate"] == 0.5
    assert audit["gates"]["activity_materialization_gte_0_50_when_requested"] is True


def test_activity_prompt_is_consumed_before_generation_prompt() -> None:
    recorder = quality.Recorder(encargo="case", request_id="request")
    recorder.pending_prompts = [("activity-system", "activity-user")]

    quality._record(
        recorder,
        "author_activity",
        {},
        {
            "activity_authoring_status": "ready",
            "authored_activity": {"activity_id": "opaque"},
        },
        None,
        None,
    )

    assert recorder.activity_system_prompt == "activity-system"
    assert recorder.activity_user_prompt == "activity-user"
    assert recorder.pending_prompts == []
