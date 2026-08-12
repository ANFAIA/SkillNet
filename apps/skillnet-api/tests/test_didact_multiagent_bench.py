from __future__ import annotations

import json
from pathlib import Path

from scripts.didact_multiagent_bench import run_experiment


FIXTURE = Path(__file__).parent / "fixtures" / "didact-selection-v1.json"


def test_multiagent_bench_covers_all_34_types_reproducibly() -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))

    first = run_experiment(raw)
    second = run_experiment(raw)

    assert first == second
    assert first["catalog_size"] == 34
    assert first["catalog_coverage"] == 1.0
    covered = {
        component
        for partition in first["specialist_partitions"].values()
        for component in partition
    }
    assert len(covered) == 34


def test_blind_arbiter_reports_quality_cost_and_declines() -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    report = run_experiment(raw)

    assert set(report["summaries"]) == {
        "central-full",
        "specialists-blind",
        "specialists-expand",
    }
    assert "strategy" not in report["arbiter_blinding"]
    assert "specialist" not in report["arbiter_blinding"]
    for summary in report["summaries"].values():
        assert 0 <= summary["mean_richness"] <= 1
        assert 0 <= summary["mean_grounding_proxy"] <= 1
        assert 0 <= summary["mean_port_feasibility"] <= 1
        assert 0 <= summary["mean_personalization_causal_change"] <= 1
        assert summary["mean_estimated_total_context_tokens"] > 0
        assert summary["mean_estimated_parallel_critical_context_tokens"] > 0
        assert summary["declines"] >= 0
