"""El planificador de evaluación (§ variedad-evaluacion-diagnostico.md)."""

from __future__ import annotations

import pytest

from src.agents.runtime.assessment import (
    DIDACT_CLOSER_ROTATION,
    DIDACT_PROCEDURE,
    DIRECT_DIDACT_BLOCKS,
    QUIZ_ROTATION,
    plan_assessment,
)
from src.agents.runtime.shape import ShapePlan, ShapeSignal
from src.render.kit import ContentFunction


def _procedure_plan() -> ShapePlan:
    return ShapePlan(
        signals=(
            ShapeSignal(kind="procedure", count=4, function=ContentFunction.PROCEDIMENTAR),
        )
    )


def _enumeration_plan() -> ShapePlan:
    return ShapePlan(
        signals=(
            ShapeSignal(kind="enumeration", count=6, function=ContentFunction.ENUMERAR),
        )
    )


def test_a_procedure_is_verified_by_dragorder() -> None:
    plan = plan_assessment(_procedure_plan(), ui_format="exercise", node_id="n1")
    assert plan.block == "DragOrder"
    assert plan.item_type is None
    assert "DragOrder" in plan.instruction()


def test_a_procedure_in_a_chart_node_does_not_become_dragorder() -> None:
    # En una pantalla `chart` la verificación no es ordenar pasos.
    plan = plan_assessment(_procedure_plan(), ui_format="chart", node_id="n1")
    assert plan.block == "QuizItem"


def test_a_non_procedure_rotates_quiz_types_and_is_stable() -> None:
    first = plan_assessment(_enumeration_plan(), ui_format="explanation", node_id="abc")
    again = plan_assessment(_enumeration_plan(), ui_format="explanation", node_id="abc")
    assert first.block == "QuizItem"
    assert first.item_type in QUIZ_ROTATION
    # Estable por nodo: misma pantalla en cada visita.
    assert first.item_type == again.item_type


def test_no_source_shape_still_yields_a_quiz() -> None:
    plan = plan_assessment(None, ui_format="explanation", node_id="xyz")
    assert plan.block == "QuizItem"
    assert plan.item_type in QUIZ_ROTATION


def test_the_rotation_spreads_across_node_ids() -> None:
    # Sobre muchos ids, la rotación toca los tres tipos y no colapsa en `test`.
    seen = {
        plan_assessment(_enumeration_plan(), ui_format="explanation", node_id=f"node-{i}").item_type
        for i in range(60)
    }
    assert seen == set(QUIZ_ROTATION)


@pytest.mark.parametrize("item_type", QUIZ_ROTATION)
def test_every_quiz_instruction_names_its_type(item_type: str) -> None:
    # La instrucción de cada tipo menciona su forma de clave, para que sea accionable.
    from src.agents.runtime.assessment import AssessmentPlan

    text = AssessmentPlan(block="QuizItem", item_type=item_type).instruction()
    assert item_type in text or (item_type == "test" and "test" in text)


def test_didact_live_closes_a_procedure_with_sort() -> None:
    plan = plan_assessment(
        _procedure_plan(), ui_format="exercise", node_id="n1", didact=True
    )
    assert plan.block == "DidactActivity"
    assert plan.item_type == DIDACT_PROCEDURE
    assert "DidactActivity" in plan.instruction()
    assert "didact.sort" in plan.instruction()
    assert "ensena" in plan.instruction()


def test_didact_live_closer_is_stable_for_the_same_node() -> None:
    first = plan_assessment(
        _enumeration_plan(), ui_format="explanation", node_id="abc", didact=True
    )
    again = plan_assessment(
        _enumeration_plan(), ui_format="explanation", node_id="abc", didact=True
    )
    assert first.item_type in {item[0] for item in DIDACT_CLOSER_ROTATION}
    assert first.block in {"DidactActivity", *DIRECT_DIDACT_BLOCKS}
    assert first.item_type == again.item_type


def test_course_position_spreads_didact_closers_across_siblings() -> None:
    types = [
        plan_assessment(
            _enumeration_plan(),
            ui_format="explanation",
            node_id=f"node-{position}",
            didact=True,
            course_id="course-a",
            position=position,
        ).item_type
        for position in range(1, 7)
    ]
    assert len(set(types)) == 6
    assert types.count("didact.quiz.true-false") <= 1


def test_legacy_position_rotation_does_not_collapse_to_true_false() -> None:
    types = [
        plan_assessment(
            _enumeration_plan(),
            ui_format="explanation",
            node_id=f"node-{position}",
            course_id="course-a",
            position=position,
        ).item_type
        for position in range(1, 7)
    ]
    assert set(types) == set(QUIZ_ROTATION)
    assert types.count("true_false") == 2


def test_live_didact_prompt_requires_authored_activity_not_quizitem() -> None:
    from src.agents.runtime.nodes import _prompt_assessment_required

    assert _prompt_assessment_required(
        {
            "assessment_block": "DidactActivity",
            "authored_activity": {"activity_id": "a1", "component_id": "didact.sort"},
        }
    ) == ("DidactActivity",)


def test_live_didact_falls_back_to_direct_closer_not_quizitem() -> None:
    from src.agents.runtime.nodes import _prompt_assessment_required

    assert _prompt_assessment_required(
        {
            "assessment_block": "DidactActivity",
            "prompt_component_ids": ["Table", "HintReveal", "Flashcard"],
        }
    ) == ("HintReveal",)
    assert _prompt_assessment_required({"assessment_block": "DidactActivity"}) == (
        "Flashcard",
    )


def test_declined_authoring_rewrites_the_verification_hint() -> None:
    from src.agents.runtime.nodes import _effective_assessment_hint

    hint = _effective_assessment_hint(
        {
            "assessment_block": "DidactActivity",
            "assessment_hint": "VERIFICA con DidactActivity usando component_id 'didact.sort'.",
        },
        ("HintReveal",),
    )
    assert "HintReveal" in hint
    assert "DidactActivity" not in hint


def test_legacy_assessment_still_requires_quizitem() -> None:
    from src.agents.runtime.nodes import _prompt_assessment_required

    assert _prompt_assessment_required({"assessment_block": "QuizItem"}) == ("QuizItem",)
    assert _prompt_assessment_required({"assessment_block": "DragOrder"}) == ("DragOrder",)


def test_direct_didact_closer_is_required_in_the_prompt() -> None:
    from src.agents.runtime.nodes import _prompt_assessment_required

    assert _prompt_assessment_required({"assessment_block": "Flashcard"}) == (
        "Flashcard",
    )


def test_activity_candidates_inject_a_planned_type_missing_from_the_shortlist() -> None:
    from src.agents.runtime.nodes import _activity_candidates

    state = {
        "assessment_item_type": "didact.matching",
        "plan_trace": {
            "selection": {
                "effective_execution": "live",
                "policy_trace": {"selected_ids": ["didact.quiz.true-false"]},
            },
            "shadow": {
                "component_candidates": [{"component_id": "didact.quiz.true-false"}]
            },
        },
    }
    assert _activity_candidates(state)[0] == "didact.matching"


def test_activity_candidates_prefer_the_planned_didact_id() -> None:
    from src.agents.runtime.nodes import _activity_candidates

    state = {
        "assessment_item_type": "didact.quiz.fill-in-the-blank",
        "plan_trace": {
            "selection": {
                "effective_execution": "live",
                "policy_trace": {
                    "selected_ids": [
                        "didact.quiz.single-choice",
                        "didact.quiz.fill-in-the-blank",
                    ]
                },
            },
            "shadow": {
                "component_candidates": [
                    {"component_id": "didact.quiz.single-choice"},
                    {"component_id": "didact.quiz.fill-in-the-blank"},
                ]
            },
        },
    }
    assert _activity_candidates(state)[0] == "didact.quiz.fill-in-the-blank"


def test_didact_verification_prompt_names_the_practice() -> None:
    from src.llm.prompts.runtime import ui_generator_system

    legacy = ui_generator_system()
    didact = ui_generator_system(didact_verification=True)
    assert "QuizItem" in legacy
    assert "verificacion Didact" in didact
    assert "DidactActivity" in didact
    assert "Flashcard" in didact
    assert "ensenar y luego practicar" in didact
    assert "El lead situa" in didact
    assert "PROHIBIDO" not in didact
