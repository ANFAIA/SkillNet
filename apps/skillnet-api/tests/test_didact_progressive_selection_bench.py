from __future__ import annotations

import json
from pathlib import Path

from scripts.didact_progressive_selection_bench import (
    RICHNESS_THRESHOLD,
    run_manifest,
)

FIXTURE = Path(__file__).parent / "fixtures" / "rich-generation-v1.json"


def _report() -> dict:
    return run_manifest(json.loads(FIXTURE.read_text(encoding="utf-8")))


def test_progressive_harness_keeps_complete_inventory_available() -> None:
    report = _report()

    assert report["inventory_size"] == 34
    progressive = [row for row in report["rows"] if row["arm"] == "progressive-34"]
    assert any(row["all_34_considered"] for row in progressive)
    assert all(1 <= len(row["selected"]) <= 2 for row in progressive)


def test_progressive_search_expands_instead_of_declining_low_richness() -> None:
    report = _report()
    progressive = [row for row in report["rows"] if row["arm"] == "progressive-34"]

    assert {row["stage"] for row in progressive} >= {"top3", "producer-full34"}
    assert all(row["selected"] for row in progressive)
    assert all(
        row["metrics"]["quality_proxy"] >= RICHNESS_THRESHOLD * 100
        or row["stage"] == "producer-full34"
        for row in progressive
    )


def test_progressive_summary_reports_tradeoffs_against_fixed_baseline() -> None:
    report = _report()
    baseline = report["summaries"]["fixed-top5"]
    progressive = report["summaries"]["progressive-34"]

    assert progressive["mean_quality_proxy"] >= baseline["mean_quality_proxy"]
    assert progressive["selection_entropy_bits"] > baseline["selection_entropy_bits"]
    assert progressive["mean_context_units"] > 3
    assert progressive["full_catalog_activation_rate"] > 0
    assert progressive["hard_gate_failures"] == 0
