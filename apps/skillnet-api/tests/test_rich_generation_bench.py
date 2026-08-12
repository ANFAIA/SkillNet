from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts/rich_generation_bench.py"
FIXTURE = ROOT / "tests/fixtures/rich-generation-v1.json"
SPEC = importlib.util.spec_from_file_location("rich_generation_bench", SCRIPT)
assert SPEC and SPEC.loader
bench = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bench
SPEC.loader.exec_module(bench)


def _report() -> dict:
    return bench.run_manifest(json.loads(FIXTURE.read_text(encoding="utf-8")))


def test_matrix_is_complete_and_reproducible() -> None:
    first = _report()
    second = _report()
    assert len(first["rows"]) == 13 * 2 * 5 * 5
    comparable = lambda row: {key: value for key, value in row.items() if key != "latency_ms"}
    assert [comparable(row) for row in first["rows"]] == [comparable(row) for row in second["rows"]]


def test_every_arm_uses_same_cells() -> None:
    report = _report()
    cells = {}
    for arm in bench.ARMS:
        cells[arm] = {
            (row["scenario"], row["profile"], row["seed"])
            for row in report["rows"]
            if row["arm"] == arm
        }
    assert len({frozenset(value) for value in cells.values()}) == 1


def test_intent_activity_is_richer_without_invalid_outputs() -> None:
    summaries = _report()["summaries"]
    intent = summaries["intent-schema-activity"]
    legacy = summaries["legacy"]
    assert intent["mean_quality"] > legacy["mean_quality"]
    assert intent["mean_affordance_coverage"] > legacy["mean_affordance_coverage"]
    assert intent["distinct_component_types"] > legacy["distinct_component_types"]
    assert intent["invalid"] == intent["ungrounded"] == intent["declines"] == 0


def test_shortlist_beats_full_catalog_for_small_fixture_decoder() -> None:
    summaries = _report()["summaries"]
    assert summaries["shortlist"]["mean_candidate_quality"] >= summaries["full-catalog"]["mean_candidate_quality"]
    assert summaries["shortlist"]["mean_prompt_tokens"] < summaries["full-catalog"]["mean_prompt_tokens"]


def test_cost_is_explicitly_zero_and_latency_is_separate() -> None:
    report = _report()
    assert report["fixture_model"] == "fixture-small/1"
    assert "not a real LLM" in report["claim_boundary"]
    assert all(summary["cost_usd"] == 0 for summary in report["summaries"].values())
    assert all(summary["mean_latency_ms"] >= 0 for summary in report["summaries"].values())


def test_boxing_regression_is_a_hard_schema_and_grounding_failure() -> None:
    report = _report()
    current = [
        row
        for row in report["rows"]
        if row["scenario"] == "boxing-defense-regression"
        and row["arm"] == "intent-activity"
    ]
    guided = [
        row
        for row in report["rows"]
        if row["scenario"] == "boxing-defense-regression"
        and row["arm"] == "intent-schema-activity"
    ]
    assert current and all(not row["valid"] and not row["grounded"] for row in current)
    assert guided and all(row["valid"] and row["grounded"] for row in guided)
