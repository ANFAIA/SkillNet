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


def _rich_plan() -> ShapePlan:
    """Material que admite CUALQUIER cierre: una relación de dos columnas y una lista.

    Sin ``procedure``, que cortocircuita la rueda hacia ``didact.sort`` antes de llegar a
    ella. Hace falta para medir el reparto entre hermanos: desde que la rueda solo ofrece
    cierres que el material sostiene, medir la variedad sobre una enumeración pelada mide
    el filtro, no el reparto.
    """
    return ShapePlan(
        signals=(
            ShapeSignal(kind="labelled_list", count=4, function=ContentFunction.ENUMERAR),
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
    assert "otro encargo" in plan.instruction()


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
    """Hermanos con el mismo material reparten los CINCO cierres que la rueda ofrece.

    Cinco y no seis, y no es una aserción debilitada: ``didact.sort`` no se alcanza nunca
    por la rueda. Tiene su propio atajo —``_has_procedure`` devuelve antes de llegar aquí—
    así que el material que lo sostiene sale por arriba y el que no lo sostiene no debe
    recibirlo. Pedirle a la rueda que ofrezca los seis sobre un material sin pasos era
    justamente el agujero: la mitad de los nodos sin forma detectable terminaban ordenando
    unos pasos que el modelo tenía que inventarse.

    El sexto cierre se cubre en ``test_material_con_pasos_recibe_el_cierre_de_ordenar``.
    """
    plans = [
        plan_assessment(
            _rich_plan(),
            ui_format="explanation",
            node_id=f"node-{position}",
            didact=True,
            course_id="course-a",
            position=position,
        )
        for position in range(1, 7)
    ]
    blocks = [plan.block for plan in plans]
    proposed = {(plan.block, plan.item_type) for plan in plans}
    assert len(proposed) == 5
    assert DIDACT_PROCEDURE not in {item_type for _block, item_type in proposed}
    assert "QuizItem" not in blocks and "DragOrder" not in blocks
    # Every closer is a real server-scored activity — never a Flashcard/reveal (owner rule).
    assert all(block == "DidactActivity" for block in blocks)
    assert not DIRECT_DIDACT_BLOCKS


def test_material_con_pasos_recibe_el_cierre_de_ordenar() -> None:
    """El sexto cierre existe, y llega exactamente cuando hay pasos que ordenar."""
    plan = plan_assessment(
        _procedure_plan(),
        ui_format="explanation",
        node_id="node-1",
        didact=True,
        course_id="course-a",
        position=1,
    )
    assert plan.item_type == DIDACT_PROCEDURE


def test_un_nodo_sin_forma_detectable_nunca_ordena_pasos_inventados() -> None:
    """Sin señales, ``didact.sort`` deja de ser admisible en todas las posiciones.

    Era el peor caso del agujero: con el conjunto admisible reducido a dos entradas, la
    mitad de los nodos sin forma pedían ordenar unos pasos que nadie había detectado.
    """
    proposed = {
        plan_assessment(
            None,
            ui_format="explanation",
            node_id=f"node-{position}",
            didact=True,
            course_id="course-a",
            position=position,
        ).item_type
        for position in range(1, 13)
    }
    assert DIDACT_PROCEDURE not in proposed


def test_a_flat_list_is_never_asked_to_be_matched_in_pairs() -> None:
    """Una enumeración no tiene pares, así que ``didact.matching`` no se propone.

    Generaliza el precedente de ``DragOrder``, que nunca se propone sin un procedimiento:
    un cierre que el material no sostiene obliga al modelo a inventarse los pares, y un par
    inventado es justo la pregunta que no se corresponde con lo explicado.
    """
    proposed = {
        plan_assessment(
            _enumeration_plan(),
            ui_format="explanation",
            node_id=f"node-{position}",
            didact=True,
            course_id="course-a",
            position=position,
        ).item_type
        for position in range(1, 13)
    }
    assert "didact.matching" not in proposed
    # Y sigue habiendo variedad real entre lo que sí sostiene el material.
    assert len(proposed) >= 4


def test_material_with_pairs_does_admit_matching() -> None:
    proposed = {
        plan_assessment(
            _rich_plan(),
            ui_format="explanation",
            node_id=f"node-{position}",
            didact=True,
            course_id="course-a",
            position=position,
        ).item_type
        for position in range(1, 13)
    }
    assert "didact.matching" in proposed


def test_a_node_with_no_shape_at_all_still_gets_a_closer() -> None:
    """Si nada encaja se recorre la rueda entera: una pantalla sin cierre no es una opción."""
    plan = plan_assessment(None, ui_format="explanation", node_id="xyz", didact=True)
    assert plan.block == "DidactActivity"
    assert plan.item_type in {item[0] for item in DIDACT_CLOSER_ROTATION}


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
    ) == ("LearningExperience",)


def test_live_didact_falls_back_to_a_real_varied_quiz_never_a_flashcard() -> None:
    from src.agents.runtime.nodes import (
        _didact_activity_fallback_item_type,
        _prompt_assessment_required,
    )

    # When no activity can be materialized the closer is a REAL check (QuizItem), never a
    # Flashcard/reveal, and its type varies by node so siblings do not all share one test.
    item_types = set()
    for node_id in ("node-1", "node-2", "node-3", "boxing-jab"):
        state = {"assessment_block": "DidactActivity", "node_id": node_id}
        required = _prompt_assessment_required(state)
        assert required == ("QuizItem",)
        item_types.add(_didact_activity_fallback_item_type(state))
    assert item_types <= set(QUIZ_ROTATION)
    assert len(item_types) > 1


def test_declined_authoring_rewrites_the_verification_hint() -> None:
    from src.agents.runtime.nodes import _effective_assessment_hint

    hint = _effective_assessment_hint(
        {
            "assessment_block": "DidactActivity",
            "assessment_hint": "VERIFICA con DidactActivity usando component_id 'didact.sort'.",
        },
        ("QuizItem",),
    )
    assert "QuizItem" in hint
    assert "DidactActivity" not in hint


def test_declined_authoring_rewrites_the_screen_scheme_practice() -> None:
    from src.agents.runtime.nodes import _effective_screen_scheme

    text = _effective_screen_scheme(
        {
            "concept_block": "Table",
            "assessment_block": "DidactActivity",
            "assessment_item_type": "didact.sort",
            "screen_scheme": "stale",
        },
        ("QuizItem",),
    )
    assert "concepto = Table" in text
    assert "QuizItem (" in text
    assert "DidactActivity" not in text


def test_legacy_assessment_still_requires_quizitem() -> None:
    from src.agents.runtime.nodes import _prompt_assessment_required

    assert _prompt_assessment_required({"assessment_block": "QuizItem"}) == ("QuizItem",)
    assert _prompt_assessment_required({"assessment_block": "DragOrder"}) == ("DragOrder",)


def test_flashcard_is_never_treated_as_an_assessment_closer() -> None:
    from src.agents.runtime.nodes import _prompt_assessment_required

    # Flashcard is CONTENT (active-recall aid), never the node's test: it is not a valid
    # assessment block, so the required-closer resolver ignores it entirely.
    assert _prompt_assessment_required({"assessment_block": "Flashcard"}) == ()


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
    assert "LearningExperience" in didact
    assert "DidactActivity(" not in didact
    assert "Flashcard" in didact
    assert "un caso, luego otro" in didact
    assert "ESQUEMA DE ESTA PANTALLA" in didact
    assert "segundo encargo" in didact
    assert "PROHIBIDO" not in didact


def test_no_content_block_is_ever_the_assessment() -> None:
    # Owner rule (2026-08-17): the TEST is always a real varied check (DidactActivity /
    # QuizItem), never a content block. No Flashcard/reveal is a closer, so the direct-block
    # rotation is empty and Flashcard never appears in the assessment rotation.
    assert not DIRECT_DIDACT_BLOCKS
    assert all(block == "DidactActivity" for _id, block in DIDACT_CLOSER_ROTATION)
    assert "Flashcard" not in {block for _id, block in DIDACT_CLOSER_ROTATION}


def test_support_only_shortlist_is_kept_interactive() -> None:
    from src.agents.runtime.nodes import (
        _SUPPORT_INTERACTIVE_IDS,
        _ensure_support_interaction,
    )

    # A passive planner shortlist gets a non-mastery interaction appended.
    kept = _ensure_support_interaction(["Table", "DidactGlossary"])
    assert any(value in _SUPPORT_INTERACTIVE_IDS for value in kept)
    # An already-interactive shortlist is left untouched. Flashcard is NOT a support
    # interaction (it is a reveal, banned as a closer), so DragOrder is the real act here.
    already = ["Table", "DragOrder"]
    assert _ensure_support_interaction(already) == already
    # A Flashcard does NOT count as the support interaction: it still gets a real one added.
    assert any(
        value in _SUPPORT_INTERACTIVE_IDS
        for value in _ensure_support_interaction(["Table", "Flashcard"])
    )
    # Even an empty shortlist gains an interaction rather than staying passive.
    assert any(value in _SUPPORT_INTERACTIVE_IDS for value in _ensure_support_interaction([]))
