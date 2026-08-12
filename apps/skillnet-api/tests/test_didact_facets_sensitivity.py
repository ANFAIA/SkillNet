from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.didact_facets_sensitivity import BENCH_VERSION, run_sensitivity


FIXTURE = Path(__file__).parent / "fixtures" / "didact-shortlist-v1.json"
SNAPSHOT = Path(__file__).parents[1] / "src" / "personalization" / "didact_snapshot.json"


def _report() -> dict:
    return run_sensitivity(
        json.loads(FIXTURE.read_text(encoding="utf-8")),
        json.loads(SNAPSHOT.read_text(encoding="utf-8")),
    )


def test_report_is_versioned_and_uses_complete_catalog() -> None:
    report = _report()
    assert report["bench_version"] == BENCH_VERSION
    assert report["catalog_size"] == 34


def test_facets_are_invariant_to_wording_only_perturbations() -> None:
    stability = _report()["wording_stability"]
    assert stability["perturbations"] == 36
    assert stability["exact_match_rate"] == 1.0
    assert stability["max_churn"] == 0.0


def test_removed_host_ports_never_leak_through_hard_gates() -> None:
    invariants = _report()["hard_gate_invariants"]
    assert invariants["profiles_checked"] == 10
    assert invariants["pass"] is True
    assert invariants["violations"] == []


def test_k5_improves_recall_and_preference_over_k3() -> None:
    policies = _report()["policies"]
    assert policies["k5"]["mean_recall"] > policies["k3"]["mean_recall"]
    assert policies["k5"]["mean_preference"] > policies["k3"]["mean_preference"]
    assert policies["k5"]["mean_size"] <= 5


def test_dynamic_policy_saves_context_without_losing_k5_quality_on_this_corpus() -> None:
    policies = _report()["policies"]
    dynamic = policies["dynamic-3-to-5"]
    assert policies["k3"]["mean_size"] < dynamic["mean_size"] < policies["k5"]["mean_size"]
    assert dynamic["mean_preference"] == policies["k5"]["mean_preference"]
    assert dynamic["mean_evidence"] == policies["k5"]["mean_evidence"]
    assert dynamic["mean_recall"] == policies["k5"]["mean_recall"]
    assert dynamic["expansion_count"] == 6


def test_presentation_preference_is_non_negative_but_weakly_causal() -> None:
    causality = _report()["preference_causality"]
    assert causality["probes"] == 4
    assert causality["non_negative_lift_rate"] == 1.0
    assert causality["mean_target_share_lift"] == pytest.approx(1 / 6)
