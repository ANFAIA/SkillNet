import json
from pathlib import Path

from scripts.experience_simulation import run_manifest


FIXTURE = Path(__file__).parent / "fixtures" / "animation-experience.json"


def _report() -> dict:
    return run_manifest(json.loads(FIXTURE.read_text(encoding="utf-8")))


def _results() -> dict[tuple[str, str], dict]:
    return {
        (result["catalogue_id"], result["profile_id"]): result
        for result in _report()["results"]
    }


def test_richer_catalogue_enables_creation_without_adding_screen_blocks() -> None:
    results = _results()
    current = results[("actual-limitado", "exploradora-visual")]
    future = results[("futuro-manipulable", "exploradora-visual")]

    assert current["declined"] is True
    assert current["decline_reasons"][0]["reason"] == "mission_unsupported"
    assert future["selected_component"] == "animation.timeline/ball-studio"
    assert future["producer_kind"] == "simulation"
    assert future["state_model_ref"] == "animation.ball-timeline/v1"
    assert "animation_submitted" in future["evidence_events"]
    assert future["preference_satisfied"] is True
    assert future["experiential_affordance_coverage"] == 1.0
    # Richness comes from what the central action permits, not extra screen blocks.
    assert future["screen_metrics"]["reachable_count"] == 2


def test_profiles_preserve_objective_but_receive_different_support_and_preferences() -> None:
    results = _results()
    visual = results[("futuro-manipulable", "exploradora-visual")]
    expert = results[("futuro-manipulable", "experto-conciso")]

    assert visual["objective_id"] == expert["objective_id"]
    assert visual["preference_satisfied"] is True
    assert expert["preference_satisfied"] is False
    assert "DECLARED_PRESENTATION_MATCHED" in visual["rationale_codes"]
    assert "DECLARED_PRESENTATION_UNAVAILABLE" in expert["rationale_codes"]
    assert visual["screen_metrics"]["critical_preservation"] == 1.0
    assert expert["screen_metrics"]["critical_preservation"] == 1.0


def test_future_component_declines_transparently_when_requirement_is_missing() -> None:
    result = _results()[("futuro-sin-requisitos", "exploradora-visual")]

    assert result["declined"] is True
    assert result["selected_component"] is None
    assert result["decline_reasons"] == (
        {
            "reason": "missing_requirements",
            "component_ids": ("animation.timeline/ball-studio",),
        },
    )


def test_every_successful_simulated_screen_remains_focused_reachable_and_safe() -> None:
    successful = [result for result in _results().values() if not result["declined"]]
    assert successful
    for result in successful:
        metrics = result["screen_metrics"]
        assert metrics["central_mission_score"] == 1.0
        assert metrics["planned_reachability"] == 1.0
        assert metrics["critical_preservation"] == 1.0
        assert metrics["orphan_reachable_ids"] == ()


def test_summary_separates_plan_success_from_experiential_richness() -> None:
    summaries = _report()["summaries"]

    assert summaries["actual-limitado"]["plan_success_rate"] == 0.0
    assert summaries["futuro-manipulable"]["plan_success_rate"] == 1.0
    assert summaries["futuro-manipulable"]["mean_experiential_affordance_coverage"] == 1.0
    assert summaries["futuro-sin-requisitos"]["plan_success_rate"] == 0.0
