import pytest

from src.personalization.plan import (
    AccessibilityCapability,
    CognitiveMission,
    ComponentDescriptor,
    DeclineReason,
    Declined,
    ErrorSignal,
    LearningExperiencePlan,
    LearningObjective,
    PersonalizationProjection,
    Presentation,
    ProducerKind,
    SourceFunction,
    SupportBand,
    plan_experience,
)


def descriptor(
    component_id: str,
    *,
    presentations: frozenset[Presentation],
    missions: frozenset[CognitiveMission] = frozenset({CognitiveMission.PRODUCE}),
    source_functions: frozenset[SourceFunction] = frozenset({SourceFunction.PROCEDURE}),
    producer_kind: ProducerKind = ProducerKind.DETERMINISTIC,
    requirements: frozenset[str] = frozenset(),
    accessibility: frozenset[AccessibilityCapability] = frozenset(),
    rank: int = 100,
) -> ComponentDescriptor:
    return ComponentDescriptor(
        component_id=component_id,
        version=1,
        missions=missions,
        source_functions=source_functions,
        presentations=presentations,
        producer_kind=producer_kind,
        requirements=requirements,
        accessibility=accessibility,
        rank=rank,
    )


@pytest.fixture
def animation_objective() -> LearningObjective:
    return LearningObjective(
        objective_id="animate-bouncing-ball",
        objective_version=1,
        mission=CognitiveMission.PRODUCE,
        source_functions=frozenset({SourceFunction.PROCEDURE}),
        available_requirements=frozenset({"timeline", "position_keyframes"}),
        required_fact_refs=("source:principles/timing",),
    )


def test_declared_simulation_selects_rich_capability_not_generic_test(
    animation_objective: LearningObjective,
) -> None:
    catalog = (
        descriptor(
            "assessment.multiple-choice",
            presentations=frozenset({Presentation.TEXT}),
            missions=frozenset({CognitiveMission.RECOGNIZE}),
            source_functions=frozenset({SourceFunction.ASSESS}),
            producer_kind=ProducerKind.ASSESSMENT,
        ),
        descriptor(
            "animation.keyframe-lab",
            presentations=frozenset({Presentation.SIMULATION}),
            producer_kind=ProducerKind.SIMULATION,
            requirements=frozenset({"timeline", "position_keyframes"}),
        ),
    )
    projection = PersonalizationProjection(
        declared_presentations=(Presentation.SIMULATION,), support_band=SupportBand.NOVICE
    )

    result = plan_experience(animation_objective, projection, catalog)

    assert isinstance(result, LearningExperiencePlan)
    assert [item.component_id for item in result.component_candidates] == [
        "animation.keyframe-lab"
    ]
    assert result.representations == (Presentation.SIMULATION,)
    assert result.support.worked_example is True
    assert "DECLARED_PRESENTATION_MATCHED" in result.rationale_codes


def test_producer_contract_is_preserved_but_does_not_replace_the_mission(
    animation_objective: LearningObjective,
) -> None:
    catalog = (
        ComponentDescriptor(
            component_id="animation.generated-keyframe-lab",
            version=1,
            missions=frozenset({CognitiveMission.PRODUCE}),
            source_functions=frozenset({SourceFunction.PROCEDURE}),
            presentations=frozenset({Presentation.SIMULATION}),
            producer_kind=ProducerKind.SIMULATION,
            affordances=frozenset({"move_keyframe", "playback"}),
            evidence_events=frozenset({"keyframe_moved", "preview_played"}),
            state_model_ref="animation-keyframes/1",
        ),
    )

    result = plan_experience(animation_objective, PersonalizationProjection(), catalog)

    assert isinstance(result, LearningExperiencePlan)
    assert result.mission is CognitiveMission.PRODUCE
    candidate = result.component_candidates[0]
    assert candidate.producer_kind is ProducerKind.SIMULATION
    assert candidate.affordances == frozenset({"move_keyframe", "playback"})
    assert candidate.evidence_events == frozenset({"keyframe_moved", "preview_played"})
    assert candidate.state_model_ref == "animation-keyframes/1"


def test_unsupported_declared_presentation_falls_back_honestly(
    animation_objective: LearningObjective,
) -> None:
    catalog = (descriptor("procedure.guide", presentations=frozenset({Presentation.TEXT})),)

    result = plan_experience(
        animation_objective,
        PersonalizationProjection(declared_presentations=(Presentation.VIDEO,)),
        catalog,
    )

    assert isinstance(result, LearningExperiencePlan)
    assert result.representations == (Presentation.TEXT,)
    assert "DECLARED_PRESENTATION_UNAVAILABLE" in result.rationale_codes
    assert "DECLARED_PRESENTATION_MATCHED" not in result.rationale_codes


def test_accessibility_is_a_hard_filter(animation_objective: LearningObjective) -> None:
    catalog = (
        descriptor(
            "animation.drag-only", presentations=frozenset({Presentation.SIMULATION}), rank=1
        ),
        descriptor(
            "animation.keyboard-lab",
            presentations=frozenset({Presentation.SIMULATION}),
            accessibility=frozenset({AccessibilityCapability.KEYBOARD}),
            rank=50,
        ),
    )
    projection = PersonalizationProjection(
        accessibility_capabilities=frozenset({AccessibilityCapability.KEYBOARD})
    )

    result = plan_experience(animation_objective, projection, catalog)

    assert isinstance(result, LearningExperiencePlan)
    assert [item.component_id for item in result.component_candidates] == [
        "animation.keyboard-lab"
    ]
    assert "ACCESSIBILITY_FILTERED" in result.rationale_codes


def test_missing_source_requirements_declines_with_a_reason(
    animation_objective: LearningObjective,
) -> None:
    catalog = (
        descriptor(
            "animation.video-reference",
            presentations=frozenset({Presentation.VIDEO}),
            requirements=frozenset({"reference_video"}),
        ),
    )

    result = plan_experience(animation_objective, PersonalizationProjection(), catalog)

    assert isinstance(result, Declined)
    assert result.reasons[-1].reason is DeclineReason.MISSING_REQUIREMENTS
    assert result.reasons[-1].component_ids == ("animation.video-reference",)


def test_planning_is_deterministic_and_preserves_objective_constraints(
    animation_objective: LearningObjective,
) -> None:
    catalog = (
        descriptor("z-component", presentations=frozenset({Presentation.TEXT}), rank=20),
        descriptor("a-component", presentations=frozenset({Presentation.TEXT}), rank=20),
    )
    projection = PersonalizationProjection(
        support_band=SupportBand.INDEPENDENT,
        error_signal=ErrorSignal.PROCEDURAL,
        density=1,
    )

    first = plan_experience(animation_objective, projection, catalog)
    second = plan_experience(animation_objective, projection, catalog)

    assert first == second
    assert isinstance(first, LearningExperiencePlan)
    assert [item.component_id for item in first.component_candidates] == [
        "a-component",
        "z-component",
    ]
    assert first.required_fact_refs == animation_objective.required_fact_refs
    assert first.support.graduated_hints is True


def test_projection_rejects_open_or_invalid_values() -> None:
    with pytest.raises(ValueError, match="density"):
        PersonalizationProjection(density=4)

    with pytest.raises(ValueError, match="duplicates"):
        PersonalizationProjection(
            declared_presentations=(Presentation.IMAGE, Presentation.IMAGE)
        )
