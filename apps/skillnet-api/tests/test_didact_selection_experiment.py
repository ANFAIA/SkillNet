from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.didact_selection_experiment import (
    BENCH_VERSION,
    load_manifest,
    run_experiment,
)


FIXTURE = Path(__file__).parent / "fixtures" / "didact-selection-v1.json"


@pytest.fixture(scope="module")
def report() -> dict:
    return run_experiment(json.loads(FIXTURE.read_text(encoding="utf-8")), repetitions=3)


def _row(report: dict, case_id: str, strategy: str) -> dict:
    return next(
        row
        for row in report["results"]
        if row["case_id"] == case_id and row["strategy"] == strategy
    )


def test_experiment_uses_all_34_descriptors_and_four_fixed_arms(report: dict) -> None:
    assert report["bench_version"] == BENCH_VERSION
    assert report["fixture_id"] == "didact-34-personalization/1"
    assert report["catalog_size"] == 34
    assert report["strategies"] == [
        "eligible-full",
        "facets-k3",
        "facets-k5",
        "facets-mmr-k5",
    ]
    assert len(report["results"]) == 10 * 4


def test_every_arm_receives_the_same_eligible_input(report: dict) -> None:
    for case_id in {row["case_id"] for row in report["results"]}:
        rows = [row for row in report["results"] if row["case_id"] == case_id]
        assert len({row["eligible_count"] for row in rows}) == 1


def test_full_is_unbounded_and_shortlists_respect_k(report: dict) -> None:
    for row in report["results"]:
        if row["strategy"] == "eligible-full":
            assert len(row["selected"]) == row["eligible_count"]
        elif row["strategy"] == "facets-k3":
            assert len(row["selected"]) <= 3
        else:
            assert len(row["selected"]) <= 5


def test_facets_recover_specialized_personalized_components(report: dict) -> None:
    expected = {
        "numeric-exploration": "didact.data-explorer",
        "decision-scenario": "didact.branching-scenario",
        "simulation-manipulation": "didact.simulation-lab",
        "code-production": "didact.code-exercise",
        "interactive-audio": "didact.interactive-media",
    }
    for case_id, component_id in expected.items():
        assert component_id in _row(report, case_id, "facets-k3")["selected"]


def test_report_exposes_requested_metrics_and_repeated_latency(report: dict) -> None:
    for summary in report["summaries"].values():
        assert summary["cases"] == 10
        for metric in (
            "mean_relevant_recall",
            "mean_affordance_coverage",
            "mean_explicit_evidence_coverage",
            "mean_prohibited_rate",
            "mean_preference_match",
            "mean_semantic_signature_diversity",
        ):
            assert 0 <= summary[metric] <= 1
        assert summary["latency_ms"]["median"] >= 0
        assert summary["latency_ms"]["p95"] >= 0


def test_missing_explicit_evidence_is_visible_not_imputed(report: dict) -> None:
    assert report["catalog_explicit_evidence_event_count"] == 0
    assert all(
        summary["mean_explicit_evidence_coverage"] == 0
        for summary in report["summaries"].values()
    )


def test_manifest_rejects_unknown_version() -> None:
    with pytest.raises(ValueError, match="fixture version"):
        load_manifest({"version": "didact-selection/99", "cases": [{}]})
