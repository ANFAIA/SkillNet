"""The planned screen scheme: how a node is taught, decided before tokens."""

from __future__ import annotations

from src.agents.runtime.assessment import AssessmentPlan, plan_assessment
from src.agents.runtime.screen_scheme import CONCEPT_BLOCKS, plan_screen_scheme
from src.agents.runtime.shape import ShapePlan, ShapeSignal
from src.llm.prompts.runtime import build_repair_prompt, build_ui_prompt
from src.render.kit import ContentFunction


def _procedure() -> ShapePlan:
    return ShapePlan(
        signals=(
            ShapeSignal(
                kind="procedure", count=4, function=ContentFunction.PROCEDIMENTAR
            ),
        )
    )


def _enumeration() -> ShapePlan:
    return ShapePlan(
        signals=(
            ShapeSignal(kind="enumeration", count=6, function=ContentFunction.ENUMERAR),
        )
    )


def _numbers() -> ShapePlan:
    return ShapePlan(
        signals=(
            ShapeSignal(
                kind="numeric_series", count=3, function=ContentFunction.CUANTIFICAR
            ),
        ),
        has_numbers=True,
    )


def _contrast() -> ShapePlan:
    return ShapePlan(
        signals=(
            ShapeSignal(kind="contrast", count=2, function=ContentFunction.CONTRASTAR),
        )
    )


def test_a_list_is_taught_as_a_table() -> None:
    assessment = plan_assessment(_enumeration(), ui_format="explanation", node_id="n1")
    scheme = plan_screen_scheme(_enumeration(), assessment, ui_format="explanation")
    assert scheme.concept_block == "Table"
    assert scheme.concept_block in CONCEPT_BLOCKS
    assert "Table" in scheme.instruction()
    assert "ESQUEMA DE ESTA PANTALLA" in scheme.instruction()


def test_a_procedure_is_taught_as_steps() -> None:
    assessment = plan_assessment(_procedure(), ui_format="exercise", node_id="n1")
    scheme = plan_screen_scheme(_procedure(), assessment, ui_format="exercise")
    assert scheme.concept_block == "StepSequence"
    assert scheme.practice_block == "DragOrder"


def test_figures_are_taught_as_a_chart() -> None:
    assessment = plan_assessment(_numbers(), ui_format="chart", node_id="n1")
    scheme = plan_screen_scheme(_numbers(), assessment, ui_format="chart")
    assert scheme.concept_block == "Chart"


def test_a_contrast_is_taught_as_before_after() -> None:
    assessment = AssessmentPlan(block="QuizItem", item_type="test")
    scheme = plan_screen_scheme(_contrast(), assessment, ui_format="explanation")
    assert scheme.concept_block == "BeforeAfter"


def test_no_shape_still_plans_a_table_not_a_definition() -> None:
    assessment = AssessmentPlan(block="QuizItem", item_type="true_false")
    scheme = plan_screen_scheme(None, assessment, ui_format="explanation")
    assert scheme.concept_block == "Table"
    assert "definicion" in scheme.instruction()


def test_a_procedure_closer_without_shape_still_asks_for_steps() -> None:
    assessment = AssessmentPlan(block="DragOrder", item_type=None)
    scheme = plan_screen_scheme(None, assessment, ui_format="mixed")
    assert scheme.concept_block == "StepSequence"


def test_practice_follows_the_assessment_plan() -> None:
    assessment = AssessmentPlan(
        block="DidactActivity", item_type="didact.quiz.single-choice"
    )
    scheme = plan_screen_scheme(_enumeration(), assessment, ui_format="explanation")
    assert scheme.practice_block == "DidactActivity"
    assert "didact.quiz.single-choice" in scheme.instruction()
    assert "otro encargo" in scheme.instruction()


def test_the_ui_prompt_carries_the_planned_scheme() -> None:
    assessment = plan_assessment(_enumeration(), ui_format="explanation", node_id="n1")
    scheme = plan_screen_scheme(_enumeration(), assessment, ui_format="explanation")
    prompt = build_ui_prompt(
        title="Alergenos",
        summary="Donde aparecen en la carta",
        screen_scheme=scheme.instruction(),
    )
    assert "ESQUEMA DE ESTA PANTALLA" in prompt
    assert "concepto = Table" in prompt


def test_the_repair_prompt_repeats_the_scheme() -> None:
    prompt = build_repair_prompt(
        previous="root = Stack([t], \"md\")",
        errors=["rule 4: too many blocks"],
        screen_scheme="ESQUEMA DE ESTA PANTALLA (ya decidido para este nodo)",
    )
    assert "ESQUEMA DE ESTA PANTALLA" in prompt
