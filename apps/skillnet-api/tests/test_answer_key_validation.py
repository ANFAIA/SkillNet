"""The render path's answer key must be gradeable, not merely present.

``missing_answer_keys`` has always asked "did the model send a solution at all".  Nothing
asked whether that solution has the right SHAPE for its ``item_type`` — while
``probe_service.validate_probe_items`` has asked exactly that for the pre-test since it was
written.  These tests pin the consequences of that gap, which are not cosmetic: each one is
an item no learner can ever pass, and the last one grades backwards.

Behaviour, not implementation: every assertion goes through ``answer_key_problems`` and the
real grader, so a reworded message cannot make them pass and a rewritten validator that
still refuses the same keys keeps them passing.
"""

from __future__ import annotations

import pytest

from src.agents.runtime.nodes import (
    answer_key_problems,
    missing_answer_keys,
    prune_answer_key,
    unusable_answer_keys,
)
from src.render.backends import get_render_backend
from src.services.exercise_service import grade

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _spec(program: str):
    return get_render_backend("openui").parse(program, ui_format="explanation")


TEST_PROGRAM = """root = Stack([intro, q1], "md")
intro = TextContent("Un cliente reclama que no le llega la entrada.", "lead")
q1 = QuizItem("q1", "test", "apply", "Como localizas su pedido?", ["Por correo", "Por nombre", "Por telefono", "Por DNI"])
"""

TRUE_FALSE_PROGRAM = """root = Stack([intro, q1], "md")
intro = TextContent("Un cliente reclama que no le llega la entrada.", "lead")
q1 = QuizItem("q1", "true_false", "understand", "El pedido se localiza por correo.", [])
"""

FILL_BLANK_PROGRAM = """root = Stack([intro, q1], "md")
intro = TextContent("Un cliente reclama que no le llega la entrada.", "lead")
q1 = QuizItem("q1", "fill_blank", "remember", "El pedido se localiza por el ____.", [])
"""

ORDER_STEPS_PROGRAM = """root = Stack([intro, q1], "md")
intro = TextContent("Un cliente reclama que no le llega la entrada.", "lead")
q1 = QuizItem("q1", "order_steps", "apply", "Ordena los pasos de la reclamacion.", ["Buscar", "Reenviar", "Registrar"])
"""


# --- test: the index has to be an in-range integer ----------------------------------


def test_a_stringified_index_is_refused_because_it_can_never_grade() -> None:
    """``"1"`` looks right and grades wrong forever: ``1 == "1"`` is ``False``."""
    spec = _spec(TEST_PROGRAM)
    key = {"q1": {"correct": "1", "explanation": "Por nombre."}}

    # The old check waves it through: an entry exists and it has a `correct` field.
    assert missing_answer_keys(spec, key) == []

    # And the grader proves why that is not good enough: the learner picks the option the
    # key names and still scores zero.
    assert grade("test", {"correct": "1", "options": []}, {"selected": 1}).score == 0.0

    problems = answer_key_problems(spec, key)
    assert problems and "q1" in problems[0]


def test_an_out_of_range_index_is_refused() -> None:
    spec = _spec(TEST_PROGRAM)
    key = {"q1": {"correct": 4, "explanation": "La quinta."}}

    assert missing_answer_keys(spec, key) == []
    assert answer_key_problems(spec, key)


def test_a_boolean_is_not_an_index_even_though_python_says_it_is() -> None:
    """``True`` is an ``int`` in Python and would silently grade as option 1."""
    spec = _spec(TEST_PROGRAM)
    assert answer_key_problems(spec, {"q1": {"correct": True}})


@pytest.mark.parametrize("index", [0, 1, 2, 3])
def test_every_real_option_index_is_accepted(index: int) -> None:
    spec = _spec(TEST_PROGRAM)
    assert answer_key_problems(spec, {"q1": {"correct": index, "explanation": "x"}}) == []


# --- true_false: the inverted-correction bug ----------------------------------------


def test_a_stringified_false_is_refused_because_it_grades_backwards() -> None:
    """The tester report of 2026-08-28, reproduced.

    ``bool("false")`` is ``True``, so the learner who answers Falso — the right answer — is
    told they were wrong and that the answer was Verdadero.
    """
    spec = _spec(TRUE_FALSE_PROGRAM)
    key = {"q1": {"correct": "false", "explanation": "Se localiza por nombre."}}

    assert missing_answer_keys(spec, key) == []

    # The inversion, demonstrated through the real grader before it is refused.
    answered_falso = grade("true_false", {"correct": "false"}, {"answer": False})
    assert answered_falso.score == 0.0

    assert answer_key_problems(spec, key)


@pytest.mark.parametrize("value", [True, False])
def test_a_real_boolean_is_accepted(value: bool) -> None:
    spec = _spec(TRUE_FALSE_PROGRAM)
    assert answer_key_problems(spec, {"q1": {"correct": value, "explanation": "x"}}) == []


def test_an_index_on_a_true_false_is_accepted_and_normalized() -> None:
    """0 y 1 se aceptan: ya corrigen bien, y rechazarlos gastaria el unico reintento.

    ``_grade_true_false`` compara ``bool(given) == bool(correct)`` y el front manda
    ``selected === 0``, asi que un entero acierta igual. Lo que hay que arreglar no es la
    correccion sino el almacenamiento: ``revealedCorrectIndex`` exige ``typeof 'boolean'``,
    asi que guardado como entero no pinta la opcion correcta y el aprendiz se queda sin
    saber cual era. ``prune_answer_key`` lo normaliza.
    """
    spec = _spec(TRUE_FALSE_PROGRAM)
    key = {"q1": {"correct": 0, "explanation": "x"}}
    assert answer_key_problems(spec, key) == []
    assert prune_answer_key(spec, key)["q1"]["correct"] is False
    assert prune_answer_key(spec, {"q1": {"correct": 1}})["q1"]["correct"] is True


def test_a_true_false_written_as_text_is_still_refused() -> None:
    """La cadena sigue prohibida: ``bool("false")`` es True e invierte la correccion."""
    spec = _spec(TRUE_FALSE_PROGRAM)
    assert answer_key_problems(spec, {"q1": {"correct": "false", "explanation": "x"}})


# --- fill_blank ----------------------------------------------------------------------


def test_an_empty_blank_is_refused() -> None:
    spec = _spec(FILL_BLANK_PROGRAM)
    assert answer_key_problems(spec, {"q1": {"blanks": ["   "]}})


def test_a_non_textual_blank_is_refused() -> None:
    spec = _spec(FILL_BLANK_PROGRAM)
    assert answer_key_problems(spec, {"q1": {"blanks": [3]}})


def test_a_real_blank_is_accepted() -> None:
    spec = _spec(FILL_BLANK_PROGRAM)
    assert answer_key_problems(spec, {"q1": {"blanks": ["correo"], "explanation": "x"}}) == []


# --- order_steps: unanswerable in the v2 renderer ------------------------------------


def test_an_order_steps_quiz_item_is_refused_whatever_its_key() -> None:
    """``QuizItemBlock`` builds a choice payload only for ``test``/``true_false``.

    Everything else posts free text, so an ``order_steps`` item is compared against a list
    of indices and scores 0.0 forever.  Ordering has a working block (``DragOrder``), so the
    repair is a swap, not a better key.
    """
    spec = _spec(ORDER_STEPS_PROGRAM)
    problems = answer_key_problems(spec, {"q1": {"correct_order": [0, 1, 2]}})
    assert problems and "DragOrder" in problems[0]


# --- ordering and scope of the check --------------------------------------------------


def test_an_absent_key_is_reported_before_a_malformed_one() -> None:
    """Two items, two different mistakes: the repair attempt must chase the missing one."""
    program = """root = Stack([intro, q1, q2], "md")
intro = TextContent("Un cliente reclama que no le llega la entrada.", "lead")
q1 = QuizItem("q1", "test", "apply", "Como lo localizas?", ["A", "B", "C", "D"])
q2 = QuizItem("q2", "test", "apply", "Y despues?", ["A", "B", "C", "D"])
"""
    spec = _spec(program)
    problems = answer_key_problems(spec, {"q1": {"correct": 9}})
    assert problems
    assert all("q2" in problem for problem in problems)


def test_a_screen_without_quiz_items_has_nothing_to_check() -> None:
    program = """root = Stack([intro, pasos], "md")
intro = TextContent("Un cliente reclama que no le llega la entrada.", "lead")
pasos = DragOrder("Ordena los pasos:", ["Buscar", "Reenviar"], ["Buscar", "Reenviar"])
"""
    spec = _spec(program)
    assert answer_key_problems(spec, {}) == []
    assert unusable_answer_keys(spec, {}) == []


def test_every_message_names_the_item_it_is_about() -> None:
    """The repair loop replays these verbatim; a message that does not name the item is
    a complaint the model cannot act on."""
    spec = _spec(TEST_PROGRAM)
    for key in ({"q1": {"correct": "1"}}, {"q1": {"correct": 7}}, {"q1": {"correct": True}}):
        problems = unusable_answer_keys(spec, key)
        assert problems and all("q1" in problem for problem in problems)
