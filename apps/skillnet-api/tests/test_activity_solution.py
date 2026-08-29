"""``activity_solution.render_solution``: one case per evaluation mode, no database.

The module is pure, so every case here is the whole test: two dictionaries in, one string
out. What is being pinned is the property the module exists for — **a learner never sees a
machine id**. ``{"source-1": "target-1"}`` is what the answer key holds; "Concepto A →
Definición A" is what may be shown, and producing it needs the public half as well.

The other half of the contract is the ``None``: an unrenderable key must not become
"source-1", must not become an empty string, and must never be what decides whether the
learner is let through.
"""

from __future__ import annotations

import pytest

from src.services.activity_authoring_validators import (
    AUTHORING_CONTRACTS,
    EVALUATED_COMPONENT_MODES,
)
from src.services.activity_solution import render_solution, revealed_solution


def _split(component_id: str) -> tuple[dict, dict]:
    """The shipped authoring example, split the way the server stores it.

    Reusing ``AUTHORING_CONTRACTS`` rather than hand-writing fixtures is the point: these
    are the exact shapes the authoring model is told to produce, so a contract that changes
    without this renderer changing breaks here instead of in front of a learner.
    """
    example = dict(AUTHORING_CONTRACTS[component_id].example)
    evaluation = dict(example.pop("evaluation"))
    return example, evaluation


def _render(component_id: str, **evaluation_overrides):
    public, evaluation = _split(component_id)
    evaluation.update(evaluation_overrides)
    return render_solution(
        component_id=component_id, public_definition=public, evaluation=evaluation
    )


# --- one case per mode -------------------------------------------------------


def test_assignments_crosses_ids_with_the_public_labels():
    rendered = _render("didact.matching")
    assert rendered == {
        "solution": "Concepto A → Definición A\nConcepto B → Definición B",
        "explanation": None,
    }
    assert "source-1" not in rendered["solution"]


def test_assignments_follows_the_authored_order_not_the_key_order():
    """The lines read in the order the learner saw the prompts, not dict insertion order."""
    public, evaluation = _split("didact.categorize")
    evaluation["expected"] = {"item-2": "category-2", "item-1": "category-1"}
    rendered = render_solution(
        component_id="didact.categorize", public_definition=public, evaluation=evaluation
    )
    assert rendered["solution"] == "Ejemplo A → Grupo A\nEjemplo B → Grupo B"


def test_word_bank_gaps_are_rebuilt_around_the_hole():
    """A gap's visible text is the sentence around it, so the placeholder goes back in."""
    rendered = _render("didact.word-bank")
    assert rendered["solution"] == "Antes ___ después → término A\nSegunda frase → término B"


def test_label_diagram_maps_targets_to_labels():
    rendered = _render("didact.label-diagram")
    assert rendered["solution"] == "Destino A → Etiqueta A"


def test_sequence_is_numbered_because_the_order_is_the_answer():
    rendered = _render("didact.sort")
    assert rendered["solution"] == "1. Primer paso\n2. Segundo paso"


def test_exact_choice_resolves_the_option_label():
    rendered = _render("didact.quiz.single-choice")
    assert rendered["solution"] == "Opción A"


def test_exact_boolean_becomes_the_word_on_the_button():
    """``didact.quiz.true-false`` has no authored labels, so the copy is fixed server-side."""
    assert _render("didact.quiz.true-false")["solution"] == "Verdadero"
    assert _render("didact.quiz.true-false", expected=False)["solution"] == "Falso"


def test_set_lists_every_selected_option():
    public, evaluation = _split("didact.quiz.multi-select")
    evaluation["expected"] = ["a", "b"]
    rendered = render_solution(
        component_id="didact.quiz.multi-select",
        public_definition=public,
        evaluation=evaluation,
    )
    assert rendered["solution"] == "Opción A\nOpción B"


def test_normalized_any_shows_only_the_canonical_variant():
    """The list is a grading tolerance, not a set of answers to recite back."""
    rendered = _render("didact.quiz.fill-in-the-blank")
    assert rendered["solution"] == "respuesta"


def test_keyed_text_pairs_each_missing_step_with_its_answer():
    rendered = _render("didact.completion-problem")
    assert rendered["solution"] == "Siguiente paso → respuesta"


def test_numeric_value_carries_the_unit_and_drops_the_trailing_zero():
    rendered = _render("didact.numeric-question")
    assert rendered["solution"] == "10 kg"


def test_numeric_range_prints_the_interval_and_never_the_tolerance():
    public, evaluation = _split("didact.numeric-question")
    rendered = render_solution(
        component_id="didact.numeric-question",
        public_definition=public,
        evaluation={"mode": "numeric", "min": 2.5, "max": 4},
    )
    assert rendered["solution"] == "2.5 – 4 kg"
    # A tolerance says how generously the server rounds. Printing it teaches the learner to
    # aim at the edge of the grading, which is not the answer.
    with_tolerance = render_solution(
        component_id="didact.numeric-question",
        public_definition=public,
        evaluation=dict(evaluation, absolute_tolerance=0.1),
    )
    assert "0.1" not in with_tolerance["solution"]


def test_regions_resolves_the_hotspot_labels():
    rendered = _render("didact.hotspot")
    assert rendered["solution"] == "Región A"


def test_every_evaluated_component_can_render_its_own_contract_example():
    """No supported component may be silently unrenderable.

    ``EVALUATED_COMPONENT_MODES`` is the list of shells whose answer the server owns. If a
    new one is added without a branch here, this fails — which is the only cheap way to
    notice, because the alternative failure is a learner stuck with no solution shown.
    """
    for component_id in EVALUATED_COMPONENT_MODES:
        rendered = _render(component_id)
        assert rendered is not None, component_id
        assert rendered["solution"].strip(), component_id


# --- the explanation ---------------------------------------------------------


def test_the_explanation_travels_when_the_author_wrote_one():
    rendered = _render("didact.quiz.single-choice", explanation="  Porque A cita la fuente. ")
    assert rendered["explanation"] == "Porque A cita la fuente."


@pytest.mark.parametrize("value", [None, "", "   ", 7])
def test_a_missing_explanation_is_none_not_an_empty_string(value):
    rendered = _render("didact.quiz.single-choice", explanation=value)
    assert rendered["explanation"] is None


# --- when nothing may be shown -----------------------------------------------


def test_an_unknown_mode_renders_nothing():
    assert (
        render_solution(
            component_id="didact.quiz.single-choice",
            public_definition={"options": [{"value": "a", "label": "Opción A"}]},
            evaluation={"mode": "llm_rubric", "expected": "a"},
        )
        is None
    )


def test_a_missing_evaluation_renders_nothing():
    assert render_solution(component_id="didact.sort", public_definition={}, evaluation=None) is None


def test_an_id_with_no_public_label_renders_nothing_rather_than_the_id():
    """The failure mode this module exists to prevent, asserted directly."""
    rendered = render_solution(
        component_id="didact.matching",
        public_definition={"sources": [{"id": "source-1", "content": "Concepto A"}], "targets": []},
        evaluation={"mode": "assignments", "expected": {"source-1": "target-1"}},
    )
    assert rendered is None


def test_a_partially_describable_key_renders_nothing_rather_than_half_an_answer():
    """Showing two of three pairs would look complete and be wrong."""
    rendered = render_solution(
        component_id="didact.matching",
        public_definition={
            "sources": [{"id": "s1", "content": "A"}, {"id": "s2", "content": "B"}],
            "targets": [{"id": "t1", "content": "1"}, {"id": "t2", "content": "2"}],
        },
        evaluation={"mode": "assignments", "expected": {"s1": "t1", "s2": "t2", "s3": "t2"}},
    )
    assert rendered is None


def test_the_raw_expected_never_appears_in_the_projection():
    public, evaluation = _split("didact.matching")
    rendered = render_solution(
        component_id="didact.matching", public_definition=public, evaluation=evaluation
    )
    assert "expected" not in rendered
    assert "target-1" not in str(rendered)


# --- the entitlement gate, shared by both grading routes ---------------------


def _activity(component_id: str = "didact.quiz.single-choice"):
    from types import SimpleNamespace

    public, evaluation = _split(component_id)
    return SimpleNamespace(
        component_id=component_id,
        public_definition=public,
        private_definition={"evaluation": evaluation},
    )


@pytest.mark.parametrize("passed, show", [(True, False), (False, True), (True, True)])
def test_either_half_of_the_gate_reveals_the_solution(passed: bool, show: bool):
    """One gate for ``/evaluate`` and ``/attempts``: ``passed or show_worked_solution``.

    They used to have one each, and the second one forgot to render anything at all.
    """
    assert revealed_solution(
        _activity(), passed=passed, show_worked_solution=show
    ) == {"solution": "Opción A", "explanation": None}


def test_an_ordinary_failure_is_told_nothing():
    assert revealed_solution(_activity(), passed=False, show_worked_solution=False) is None


def test_an_unrenderable_mode_is_promised_and_not_delivered():
    """``show_worked_solution: true`` with ``solution: null`` is reachable, by design.

    Unblocking is ``Transition.show_worked_solution``'s job and is decided without ever
    consulting this module, so a key this module cannot render honestly still lets the
    learner out — with nothing to read. A client must choose its copy from ``solution``,
    never from the flag, or it paints an empty "here is the answer" panel.
    """
    activity = _activity()
    activity.private_definition = {"evaluation": {"mode": "provider_specific"}}

    assert revealed_solution(activity, passed=False, show_worked_solution=True) is None
