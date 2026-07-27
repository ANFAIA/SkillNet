"""``content_for()``: the adapter between v2 items and the v1 grader. No DB, no network.

The load-bearing claim is that a v2 item graded through the adapter scores **exactly**
what the same content scored in v1, including the "no partial credit" property that
§7.2's arithmetic depends on. So every test here compares against ``grade()`` called
directly with a v1 ``content`` dict.
"""

import pytest

from src.core.exceptions import ValidationError
from src.services.exercise_service import grade
from src.services.node_grading import (
    classify_error,
    content_for,
    grade_item,
    item_type_of,
    public_props,
    split_v1_content,
)

# One canonical v1 `content` per type, in the exact shapes of the generation prompt.
V1_CONTENT = {
    "test": {
        "question": "Un cliente devuelve un articulo a los 20 dias con ticket. Que procede?",
        "options": [
            "Rechazar la devolucion",
            "Aceptarla y devolver el importe",
            "Aceptarla solo como vale",
            "Pedir autorizacion al fabricante",
        ],
        "correct": 1,
        "explanation": "El plazo es de 30 dias con ticket.",
    },
    "true_false": {
        "statement": "El plazo de devolucion es de 30 dias.",
        "correct": True,
        "explanation": "Asi lo fija la politica.",
    },
    "fill_blank": {
        "template": "El plazo de devolucion con ticket es de ___ dias.",
        "blanks": ["30"],
        "explanation": "Treinta dias naturales.",
    },
    "order_steps": {
        "instruction": "Ordena los pasos de una devolucion.",
        "steps": ["Comprobar el ticket", "Revisar el articulo", "Emitir el reembolso"],
        "correct_order": [0, 1, 2],
        "explanation": "Primero el ticket, luego el articulo.",
    },
    "practical_case": {
        "context": "Un cliente sin ticket insiste.",
        "question": "Como lo gestionas?",
        "rubric": [{"criteria": "Menciona el vale", "required": True}],
        "explanation": "Sin ticket, vale.",
    },
    "dialogue": {
        "context": "Cliente enfadado en caja.",
        "system_prompt": "Actua como un cliente molesto.",
        "max_turns": 4,
        "evaluation_criteria": ["Mantiene la calma"],
    },
}

DETERMINISTIC = ("test", "true_false", "fill_blank", "order_steps")

# The answer that scores 1.0, and one that scores 0.0, per deterministic type.
RIGHT_ANSWER = {
    "test": {"selected": 1},
    "true_false": {"answer": True},
    "fill_blank": {"answers": ["30"]},
    "order_steps": {"order": [0, 1, 2]},
}
WRONG_ANSWER = {
    "test": {"selected": 0},
    "true_false": {"answer": False},
    "fill_blank": {"answers": ["15"]},
    "order_steps": {"order": [1, 0, 2]},
}


@pytest.mark.parametrize("item_type", DETERMINISTIC)
def test_split_then_content_for_round_trips_the_v1_content(item_type):
    """The adapter recombines props + answer_key into exactly the original content."""
    original = V1_CONTENT[item_type]
    props, key = split_v1_content(item_type, original, item_id="a", bloom_level="apply")
    assert content_for(props, key) == original


@pytest.mark.parametrize("item_type", ["practical_case", "dialogue"])
def test_round_trip_for_the_open_types(item_type):
    original = V1_CONTENT[item_type]
    props, key = split_v1_content(item_type, original, item_id="c", bloom_level="apply")
    assert content_for(props, key) == original


@pytest.mark.parametrize("item_type", DETERMINISTIC)
def test_grading_through_the_adapter_matches_v1_exactly(item_type):
    original = V1_CONTENT[item_type]
    props, key = split_v1_content(item_type, original, item_id="a", bloom_level="apply")

    for answer in (RIGHT_ANSWER[item_type], WRONG_ANSWER[item_type]):
        v1 = grade(item_type, original, answer)
        v2 = grade_item(props, key, answer)
        assert (v2.score, v2.passed) == (v1.score, v1.passed), answer
        assert v2.explanation == v1.explanation


@pytest.mark.parametrize("item_type", DETERMINISTIC)
def test_no_partial_credit(item_type):
    """0.0 or 1.0, never anything in between. §7.2's arithmetic depends on it."""
    original = V1_CONTENT[item_type]
    props, key = split_v1_content(item_type, original, item_id="a", bloom_level="apply")
    assert grade_item(props, key, RIGHT_ANSWER[item_type]).score == 1.0
    assert grade_item(props, key, WRONG_ANSWER[item_type]).score == 0.0


def test_fill_blank_fails_on_a_single_wrong_blank():
    props = {
        "item_id": "c",
        "item_type": "fill_blank",
        "template": "De ___ a ___ dias.",
    }
    key = {"blanks": ["1", "30"]}
    assert grade_item(props, key, {"answers": ["1", "30"]}).score == 1.0
    assert grade_item(props, key, {"answers": ["1", "31"]}).score == 0.0
    # A missing blank is a failure, not a crash.
    assert grade_item(props, key, {"answers": ["1"]}).score == 0.0


def test_v2_quiz_item_props_use_question_for_every_type():
    """A ``QuizItem`` only has ``question``, so the adapter has to accept it as the
    statement / template / instruction of the v1 shapes."""
    tf = content_for(
        {"item_id": "b", "item_type": "true_false", "question": "Son 30 dias."},
        {"correct": True},
    )
    assert tf["statement"] == "Son 30 dias."
    assert grade("true_false", tf, {"answer": True}).score == 1.0

    fb = content_for(
        {"item_id": "c", "item_type": "fill_blank", "question": "Son ___ dias."},
        {"blanks": ["30"]},
    )
    assert fb["template"] == "Son ___ dias."
    assert grade("fill_blank", fb, {"answers": ["30"]}).score == 1.0

    steps = content_for(
        {
            "item_id": "c",
            "item_type": "order_steps",
            "question": "Ordena.",
            "options": ["uno", "dos"],
        },
        {"correct_order": [0, 1]},
    )
    assert steps["instruction"] == "Ordena."
    assert steps["steps"] == ["uno", "dos"]
    assert grade("order_steps", steps, {"order": [0, 1]}).score == 1.0


def test_a_missing_answer_key_can_never_pass():
    """An item served without its key grades 0.0. Failing closed matters: the whole
    point of a separate ``answer_key`` column is that a leak is impossible, and the
    fallback must not be "everybody passes"."""
    for item_type in DETERMINISTIC:
        props, _key = split_v1_content(
            item_type, V1_CONTENT[item_type], item_id="a", bloom_level="apply"
        )
        result = grade_item(props, None, RIGHT_ANSWER[item_type])
        assert result.score == 0.0
        assert result.passed is False


def test_public_props_drops_a_misplaced_answer():
    leaked = {
        "item_id": "a",
        "item_type": "test",
        "question": "?",
        "options": ["a", "b", "c", "d"],
        "correct": 2,
        "explanation": "porque",
    }
    served = public_props(leaked)
    assert "correct" not in served
    assert "explanation" not in served
    assert served["options"] == ["a", "b", "c", "d"]


def test_item_type_accepts_both_names_and_rejects_neither():
    assert item_type_of({"item_type": "test"}) == "test"
    assert item_type_of({"type": "test"}) == "test"
    with pytest.raises(ValidationError):
        item_type_of({"question": "?"})


def test_unknown_type_is_a_validation_error():
    with pytest.raises(ValidationError):
        content_for({"item_id": "a", "item_type": "sudoku"}, {})
    with pytest.raises(ValidationError):
        split_v1_content("sudoku", {}, item_id="a")


# --- §7.4 error classification ----------------------------------------------


def test_classify_detail_is_only_form():
    props = {"item_id": "c", "item_type": "fill_blank", "template": "___"}
    key = {"blanks": ["treinta dias"]}
    # Accents and punctuation only -> the content was right.
    assert classify_error(props, key, {"answers": ["treinta, dias"]}) == "detail"
    assert classify_error(props, key, {"answers": ["Treinta días"]}) == "detail"


def test_classify_procedural_is_the_right_pieces_in_the_wrong_place():
    swapped = {"item_id": "c", "item_type": "fill_blank", "template": "___ y ___"}
    assert (
        classify_error(swapped, {"blanks": ["30", "14"]}, {"answers": ["14", "30"]})
        == "procedural"
    )
    steps = {"item_id": "c", "item_type": "order_steps", "steps": ["a", "b", "c"]}
    assert (
        classify_error(steps, {"correct_order": [0, 1, 2]}, {"order": [2, 1, 0]})
        == "procedural"
    )


def test_classify_conceptual_is_the_honest_default():
    props = {"item_id": "a", "item_type": "test", "options": ["a", "b", "c", "d"]}
    assert classify_error(props, {"correct": 1}, {"selected": 3}) == "conceptual"
    blanks = {"item_id": "c", "item_type": "fill_blank", "template": "___"}
    assert classify_error(blanks, {"blanks": ["30"]}, {"answers": ["90"]}) == "conceptual"
    assert classify_error(blanks, {"blanks": ["30"]}, {"answers": []}) == "conceptual"
