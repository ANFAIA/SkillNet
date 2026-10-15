"""``exercise_content_problems`` — the answer key's shape, checked before publish.

An exercise whose key cannot be graded grades every learner 0.0 forever, so it can never
be passed and it blocks the course. The generator prompt states the shape of each type but
nothing verified it; the quality reviewer is best-effort and reads prose, not shapes. This
is the deterministic gate ``publish`` uses to drop an ungradeable exercise.
"""

from __future__ import annotations

import pytest

from src.agents.content.helpers import exercise_content_problems


def test_a_well_formed_test_has_no_problems() -> None:
    content = {
        "question": "El descuadre es de seis euros. Que haces?",
        "options": ["Cerrar", "Avisar al encargado", "Repetir", "Dejarlo"],
        "correct": 1,
        "explanation": "Por encima de cinco euros se avisa al encargado.",
    }
    assert exercise_content_problems("test", content) == []


def test_a_test_whose_correct_index_is_out_of_range_is_rejected() -> None:
    content = {"options": ["A", "B", "C"], "correct": 3}
    problems = exercise_content_problems("test", content)
    assert problems and "outside" in problems[0]


def test_a_test_whose_correct_is_a_boolean_is_rejected() -> None:
    # ``isinstance(True, int)`` is True in Python, so the bool check has to come first.
    content = {"options": ["A", "B"], "correct": True}
    assert exercise_content_problems("test", content)


def test_a_fill_blank_with_the_wrong_number_of_answers_is_rejected() -> None:
    content = {"template": "Se avisa al ____ y se anota en el ____.", "blanks": ["encargado"]}
    problems = exercise_content_problems("fill_blank", content)
    assert problems and "2 hole(s) but 1 blank" in problems[0]


def test_a_fill_blank_with_no_hole_is_rejected() -> None:
    assert exercise_content_problems("fill_blank", {"template": "Sin hueco.", "blanks": []})


def test_a_fill_blank_with_matching_holes_is_accepted() -> None:
    content = {"template": "Se avisa al ____ antes de cerrar.", "blanks": ["encargado"]}
    assert exercise_content_problems("fill_blank", content) == []


def test_order_steps_must_be_a_permutation() -> None:
    content = {"steps": ["Uno", "Dos", "Tres"], "correct_order": [0, 1]}
    assert exercise_content_problems("order_steps", content)
    good = {"steps": ["Uno", "Dos", "Tres"], "correct_order": [2, 0, 1]}
    assert exercise_content_problems("order_steps", good) == []


def test_true_false_needs_a_boolean() -> None:
    assert exercise_content_problems("true_false", {"correct": "si"})
    assert exercise_content_problems("true_false", {"correct": False}) == []


def test_practical_case_needs_a_context_a_question_and_a_rubric() -> None:
    content = {"context": "Un cliente...", "question": "Que haces?", "rubric": []}
    assert exercise_content_problems("practical_case", content)


@pytest.mark.parametrize("content", [None, "texto", []])
def test_non_object_content_is_rejected(content: object) -> None:
    assert exercise_content_problems("test", content)


def test_an_unknown_type_is_reported() -> None:
    assert exercise_content_problems("quiz", {})
