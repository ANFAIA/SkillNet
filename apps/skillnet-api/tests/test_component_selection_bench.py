from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.component_selection_bench import BENCH_VERSION, load_manifest, run_manifest


FIXTURE = Path(__file__).parent / "fixtures" / "component-selection-v1.json"


@pytest.fixture(scope="module")
def report() -> dict:
    return run_manifest(json.loads(FIXTURE.read_text(encoding="utf-8")))


def _row(report: dict, case_id: str, strategy: str) -> dict:
    return next(
        row
        for row in report["results"]
        if row["case_id"] == case_id and row["strategy"] == strategy
    )


def test_report_is_versioned_and_contains_every_strategy(report: dict) -> None:
    assert report["bench_version"] == BENCH_VERSION
    assert report["fixture_id"] == "legacy-openui-capabilities/1"
    assert report["catalog_version"].startswith("skillnet-ui/")
    assert report["strategies"] == [
        "eligible-full",
        "facets-top-k",
        "lexical-diverse-top-k",
    ]
    assert len(report["results"]) == 6 * 3


def test_hard_filters_report_each_stage_and_remove_missing_requirements(report: dict) -> None:
    row = _row(report, "recognize-by-recall", "eligible-full")
    assert [step["name"] for step in row["filters"]] == [
        "mission",
        "source_function",
        "requirements",
        "accessibility",
    ]
    requirements = next(step for step in row["filters"] if step["name"] == "requirements")
    assert "AudioExplanation" in requirements["rejected"]
    assert all(item["component_id"] != "AudioExplanation" for item in row["shortlist"])


def test_eligible_full_is_not_truncated_but_other_strategies_are(report: dict) -> None:
    full = _row(report, "reconstruct-procedure", "eligible-full")
    facets = _row(report, "reconstruct-procedure", "facets-top-k")
    lexical = _row(report, "reconstruct-procedure", "lexical-diverse-top-k")
    assert len(full["shortlist"]) == full["eligible_count"]
    assert len(facets["shortlist"]) <= report["top_k"]
    assert len(lexical["shortlist"]) <= report["top_k"]
    assert len({item["component_id"] for item in lexical["shortlist"]}) == len(lexical["shortlist"])


def test_facets_prioritize_observable_evidence(report: dict) -> None:
    row = _row(report, "decide-with-evidence", "facets-top-k")
    ids = [item["component_id"] for item in row["shortlist"]]
    assert ids[:2] == ["QuizItem", "DragOrder"]
    assert row["metrics"]["evidence_coverage"] == 1.0
    assert row["metrics"]["forbidden_count"] == 0


def test_lexical_strategy_uses_relevance_and_novelty(report: dict) -> None:
    row = _row(report, "recognize-by-recall", "lexical-diverse-top-k")
    assert row["shortlist"][0]["component_id"] == "Flashcard"
    assert row["shortlist"][0]["scores"]["lexical"] > 0
    assert all("novelty" in item["scores"] for item in row["shortlist"])
    assert row["metrics"]["hit"] is True


def test_summary_exposes_retrieval_quality_and_latency(report: dict) -> None:
    for summary in report["summaries"].values():
        assert summary["cases"] == 6
        assert 0 <= summary["hit_rate"] <= 1
        assert 0 <= summary["mean_relevant_recall"] <= 1
        assert 0 <= summary["mean_affordance_coverage"] <= 1
        assert summary["latency_ms"]["p95"] >= 0


def test_manifest_rejects_unknown_version() -> None:
    with pytest.raises(ValueError, match="fixture version"):
        load_manifest({"version": "component-selection/99", "cases": [{}]})
