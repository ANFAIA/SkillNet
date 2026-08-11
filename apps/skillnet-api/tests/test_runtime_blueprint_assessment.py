"""El blueprint impone el plan de evaluacion sobre lo que decida el LLM.

Fija el comportamiento de ``_apply_assessment``: la variedad de evaluacion no puede quedar
a merced del modelo, asi que el bloque de cierre se reescribe al plan determinista, y un
procedimiento (StepSequence) se verifica siempre ordenandolo (DragOrder).
"""

from __future__ import annotations

from src.agents.runtime.agents.blueprint import _apply_assessment, _ensure_verification
from src.agents.runtime.agents.types import Blueprint, BlueprintBlock
from src.agents.runtime.assessment import AssessmentPlan


def _bp(*types_and_intents: tuple[str, str, str]) -> Blueprint:
    return Blueprint(
        blocks=[
            BlueprintBlock(id=bid, type=btype, intent=intent)  # type: ignore[arg-type]
            for bid, btype, intent in types_and_intents
        ]
    )


def test_it_forces_the_planned_quiz_item_type() -> None:
    # El LLM cerro con un test; el plan pide fill_blank -> gana el plan.
    bp = _bp(("intro", "TextContent", "enganchar"), ("q1", "QuizItem", "verificar"))
    out = _apply_assessment(
        bp, AssessmentPlan(block="QuizItem", item_type="fill_blank"), "understand", "explanation"
    )
    last = out.blocks[-1]
    assert last.type == "QuizItem"
    assert last.item_type == "fill_blank"


def test_it_converts_a_quiz_to_dragorder_when_the_plan_says_so() -> None:
    bp = _bp(("intro", "TextContent", "enganchar"), ("q1", "QuizItem", "verificar"))
    out = _apply_assessment(
        bp, AssessmentPlan(block="DragOrder", item_type=None), "apply", "exercise"
    )
    assert out.blocks[-1].type == "DragOrder"


def test_a_step_sequence_concept_is_verified_by_reordering_it() -> None:
    # Aunque el plan sea un QuizItem, una StepSequence en pantalla se cierra con DragOrder.
    bp = _bp(
        ("intro", "TextContent", "enganchar"),
        ("pasos", "StepSequence", "concepto"),
        ("q1", "QuizItem", "verificar"),
    )
    out = _apply_assessment(
        bp, AssessmentPlan(block="QuizItem", item_type="test"), "apply", "exercise"
    )
    assert out.blocks[-1].type == "DragOrder"


def test_a_step_sequence_in_a_chart_node_does_not_force_dragorder() -> None:
    bp = _bp(
        ("intro", "TextContent", "enganchar"),
        ("pasos", "StepSequence", "concepto"),
        ("q1", "QuizItem", "verificar"),
    )
    out = _apply_assessment(
        bp, AssessmentPlan(block="QuizItem", item_type="test"), "apply", "chart"
    )
    assert out.blocks[-1].type == "QuizItem"


def test_ensure_verification_appends_a_quiz_when_missing() -> None:
    bp = _bp(("intro", "TextContent", "enganchar"), ("tabla", "Table", "concepto"))
    out = _ensure_verification(bp, "explanation", "understand")
    assert out.blocks[-1].type in ("QuizItem", "DragOrder")
