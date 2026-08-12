from dataclasses import asdict

import pytest

from src.personalization.plan import (
    AccessibilityCapability,
    ErrorSignal,
    InferredPresentationBucket,
    SupportBand,
)
from src.personalization.projection import project_runtime_signals


def test_calibration_suppresses_inferred_vector_but_keeps_declared_support() -> None:
    projection = project_runtime_signals(
        experience_level="none",
        preset="focus",
        format_vector={"texto": 0.05, "ejercicio": 0.95},
        nodes_completed=2,
    )

    assert projection.calibrating is True
    assert projection.inferred_presentation_bucket is InferredPresentationBucket.UNKNOWN
    assert projection.support_band is SupportBand.NOVICE
    assert projection.density == 2


@pytest.mark.parametrize(
    ("vector", "expected"),
    [
        ({"texto": 0.7, "ejercicio": 0.3}, InferredPresentationBucket.TEXT_HIGH),
        ({"ejercicio": 0.7, "texto": 0.3}, InferredPresentationBucket.EXERCISE_HIGH),
        ({"dato": 0.7, "texto": 0.3}, InferredPresentationBucket.DATA_HIGH),
        ({"codigo": 1.0}, InferredPresentationBucket.UNKNOWN),
        ({"dato": "invalid"}, InferredPresentationBucket.UNKNOWN),
    ],
)
def test_post_calibration_vector_is_compiled_to_closed_bucket(vector, expected) -> None:
    projection = project_runtime_signals(format_vector=vector, nodes_completed=3)

    assert projection.calibrating is False
    assert projection.inferred_presentation_bucket is expected


def test_current_accessibility_and_error_signals_are_preserved_without_raw_values() -> None:
    projection = project_runtime_signals(
        accessibility={
            "short_blocks": True,
            "reduce_motion": True,
            "high_contrast": True,
            "extra_time": True,
            "future_unknown_flag": True,
        },
        last_error_kind="detail",
        base_density=3,
    )

    assert projection.density == 2
    assert projection.error_signal is ErrorSignal.DETAIL
    assert projection.accessibility_capabilities == frozenset(
        {
            AccessibilityCapability.REDUCED_MOTION,
            AccessibilityCapability.HIGH_CONTRAST,
            AccessibilityCapability.EXTRA_TIME,
        }
    )


def test_fast_preset_is_compiled_to_small_density_and_expert_to_independent() -> None:
    projection = project_runtime_signals(
        experience_level="experienced", preset="fast", base_density=3
    )

    assert projection.support_band is SupportBand.INDEPENDENT
    assert projection.density == 1


def test_frozen_scaffold_band_overrides_declared_experience() -> None:
    projection = project_runtime_signals(
        experience_level="experienced", scaffold_band="novice"
    )

    assert projection.support_band is SupportBand.NOVICE


def test_role_and_sector_cannot_change_or_leak_into_projection() -> None:
    first = project_runtime_signals(role_title="Camarero", sector="Hosteleria")
    second = project_runtime_signals(role_title="Animador", sector="Cine")

    assert first == second
    serialized = repr(asdict(first))
    assert "Camarero" not in serialized
    assert "Hosteleria" not in serialized
    assert set(asdict(first)) == {
        "declared_presentations",
        "inferred_presentation_bucket",
        "support_band",
        "density",
        "accessibility_capabilities",
        "error_signal",
        "calibrating",
        "projection_version",
    }


def test_projection_api_rejects_identity_and_memory_inputs() -> None:
    with pytest.raises(TypeError):
        project_runtime_signals(user_id="user-123")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        project_runtime_signals(memory_md="raw learner memory")  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ("conceptual", ErrorSignal.CONCEPTUAL),
        ("procedural", ErrorSignal.PROCEDURAL),
        ("transfer", ErrorSignal.TRANSFER),
        ("unknown", ErrorSignal.NONE),
        (None, ErrorSignal.NONE),
    ],
)
def test_error_vocabulary_is_closed(error, expected) -> None:
    assert project_runtime_signals(last_error_kind=error).error_signal is expected
