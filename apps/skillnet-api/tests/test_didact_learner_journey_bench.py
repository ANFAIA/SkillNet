from __future__ import annotations

import json
from pathlib import Path

from scripts.didact_learner_journey_bench import run_manifest

FIXTURE = Path(__file__).parent / "fixtures" / "didact-learner-journeys-v1.json"


def _report() -> dict:
    return run_manifest(json.loads(FIXTURE.read_text(encoding="utf-8")))


def test_every_longitudinal_render_considers_the_complete_didact_inventory() -> None:
    report = _report()
    assert report["inventory_size"] == 34
    assert report["summary"]["all_renders_considered_34"] is True
    assert report["render_count"] == 24


def test_profiles_diverge_without_changing_the_course_objective_or_facts() -> None:
    report = _report()
    stages = report["summary"]["stage_diversity"]
    assert report["summary"]["objective_and_fact_stability"] == 1.0
    assert stages["onboarding-render"]["distinct_render_signatures"] >= 3
    assert stages["settings-regeneration"]["distinct_render_signatures"] >= 3
    assert all(value["decline_rate"] == 0 for value in stages.values())


def test_on_the_fly_counterfactuals_expose_which_signals_actually_change_output() -> None:
    axes = _report()["summary"]["causal_adaptation"]
    assert axes["error"]["causal_change_rate"] > 0
    assert axes["settings"]["causal_change_rate"] == 1.0
    # Declared preferences remain authoritative, while at least the profile without a
    # declared presentation now adapts causally from its learned post-calibration vector.
    assert 0 < axes["format_vector"]["causal_change_rate"] < 1


def test_cache_is_stable_during_calibration_and_invalidates_afterward() -> None:
    report = _report()
    assert report["summary"]["cache_check_pass_rate"] == 1.0
    assert all(item["passed"] for item in report["cache_checks"])


def test_every_profile_reaches_completion_and_recovery_stage() -> None:
    report = _report()
    assert report["summary"]["completion_rate"] == 1.0
    assert report["summary"]["progression_integrity"] == 1.0
    assert report["summary"]["error_recovery_coverage"] == 1.0
    rows = report["rows"]
    profile_ids = {row["profile_id"] for row in rows}
    assert {
        row["profile_id"]
        for row in rows
        if row["stage"] == "recovery-next-render"
    } == profile_ids
