from __future__ import annotations

import json
from pathlib import Path

from scripts.didact_shortlist_experiment import (
    BENCH_VERSION,
    RETRIEVAL_BACKEND,
    STRATEGIES,
    load_fixture,
    run_experiment,
)


FIXTURE = Path(__file__).parent / "fixtures" / "didact-shortlist-v1.json"
SNAPSHOT = Path(__file__).parents[1] / "src" / "personalization" / "didact_snapshot.json"


def _report() -> dict:
    return run_experiment(
        json.loads(FIXTURE.read_text(encoding="utf-8")),
        json.loads(SNAPSHOT.read_text(encoding="utf-8")),
    )


def test_report_is_reproducibly_configured_and_honest_about_semantics() -> None:
    report = _report()
    assert report["bench_version"] == BENCH_VERSION
    assert report["retrieval_backend"] == RETRIEVAL_BACKEND
    assert report["embedding_backend"] is None
    assert report["strategies"] == list(STRATEGIES)
    assert report["configuration"]["hard_gates"] == [
        "mission",
        "source_function",
        "requirements",
        "accessibility",
    ]


def test_each_policy_runs_on_the_same_cases_and_only_after_hard_gates() -> None:
    report = _report()
    assert len(report["results"]) == 12 * len(STRATEGIES)
    for row in report["results"]:
        assert [item["name"] for item in row["filters"]] == report["configuration"][
            "hard_gates"
        ]
        assert row["metrics"]["forbidden_count"] == 0


def test_top5_strategies_are_bounded_and_full_baseline_is_not() -> None:
    report = _report()
    for row in report["results"]:
        if row["strategy"] == "eligible-full":
            assert len(row["shortlist"]) == row["eligible_count"]
        else:
            assert len(row["shortlist"]) <= 5


def test_summary_reports_requested_quality_variety_and_latency_metrics() -> None:
    report = _report()
    for summary in report["summaries"].values():
        for metric in (
            "mean_relevant_recall",
            "mean_evidence_coverage",
            "mean_affordance_coverage",
            "mean_preference_coverage",
            "catalog_variety",
            "mean_intra_shortlist_diversity",
        ):
            assert 0 <= summary[metric] <= 1
        assert summary["unique_components"] > 0
        assert summary["latency_ms"]["p95"] >= 0


def test_fixture_requires_fixed_top_five() -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["top_k"] = 4
    try:
        load_fixture(raw)
    except ValueError as error:
        assert "top_k" in str(error)
    else:
        raise AssertionError("top_k=4 should be rejected")
