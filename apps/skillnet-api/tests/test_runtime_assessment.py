"""El planificador de evaluación (§ variedad-evaluacion-diagnostico.md)."""

from __future__ import annotations

import pytest

from src.agents.runtime.assessment import QUIZ_ROTATION, plan_assessment
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
