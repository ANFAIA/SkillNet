from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.experience_intent_bench import BENCH_VERSION, load_manifest, run_manifest


FIXTURE = Path(__file__).parent / "fixtures" / "experience-intent-v1.json"


@pytest.fixture(scope="module")
def report() -> dict:
    return run_manifest(json.loads(FIXTURE.read_text(encoding="utf-8")), iterations=10)


def test_benchmark_uses_complete_didact_catalog_and_two_input_adapters(report: dict) -> None:
    assert report["bench_version"] == BENCH_VERSION
    assert report["catalog_size"] == 34
    assert set(report["summaries"]) == {"direct", "experience-intent"}
    assert len(report["results"]) == 18


def test_typed_intent_has_no_component_names() -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    serialized = json.dumps(
        [case["experience_intent"] for case in raw["cases"]], ensure_ascii=False
    ).lower()
    assert "didact." not in serialized
    assert not any(
        term in serialized
        for term in ("flashcard", "quiz", "timeline", "worked-example")
    )


def test_experience_first_improves_quality_and_causal_personalization(report: dict) -> None:
    direct = report["summaries"]["direct"]
    typed = report["summaries"]["experience-intent"]

    assert typed["mean_quality"] > direct["mean_quality"] + 0.20
    assert typed["causal_pair_change_rate"] == 1.0
    assert typed["causal_pair_change_rate"] > direct["causal_pair_change_rate"]
    assert typed["mean_pair_selection_distance"] > direct["mean_pair_selection_distance"]


def test_experience_first_increases_useful_semantic_variety(report: dict) -> None:
    direct = report["summaries"]["direct"]
    typed = report["summaries"]["experience-intent"]

    assert typed["useful_semantic_signatures"] > direct["useful_semantic_signatures"]
    assert typed["useful_semantic_entropy_bits"] > direct["useful_semantic_entropy_bits"]


def test_both_strategies_decline_an_unsupported_accessibility_contract(report: dict) -> None:
    rows = [
        row for row in report["results"] if row["case_id"] == "unsupported-switch-access"
    ]
    assert len(rows) == 2
    assert all(row["declined"] and row["decline_correct"] for row in rows)


def test_latency_is_measured_but_not_part_of_quality(report: dict) -> None:
    for summary in report["summaries"].values():
        assert summary["latency_ms"]["p50"] >= 0
        assert summary["latency_ms"]["p95"] >= summary["latency_ms"]["p50"]
    assert "latency_ms" not in report["weights"]


def test_manifest_rejects_unknown_version() -> None:
    with pytest.raises(ValueError, match="fixture version"):
        load_manifest({"version": "experience-intent/99", "cases": []})
