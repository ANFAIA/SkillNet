"""The frozen catalogue (§5.3) and the 7 contract rules of §5.2.

No DB, no network. The prompt is no longer built here — ``library.prompt()`` writes it at
build time and ``tests/test_render_prompt_artifact.py`` guards it against drift.
"""

from __future__ import annotations

import pytest

from src.models.exercise import ExerciseType
from src.render import (
    UI_KIT,
    RenderValidationError,
    parse_spec,
)
from src.render.kit import PropKind

# The table of §5.3, verbatim: name -> positional prop order.
EXPECTED_CATALOGUE: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Stack", ("children", "gap")),
    ("TextContent", ("text", "variant")),
    ("Card", ("title", "children")),
    ("Callout", ("tone", "text")),
    ("StepSequence", ("title", "steps")),
    ("Table", ("headers", "rows")),
    ("CodeBlock", ("language", "code")),
    ("Chart", ("kind", "title", "labels", "values")),
    ("QuizItem", ("item_id", "item_type", "bloom_level", "question", "options")),
    ("SliderExploration", ("title", "variable", "min", "max", "step", "formula", "description")),
    ("ManipulableGraph", ("title", "xLabel", "yLabel", "points", "functions")),
    ("BeforeAfter", ("title", "beforeLabel", "beforeContent", "afterLabel", "afterContent")),
    ("Markdown", ("content",)),
    ("DragOrder", ("instruction", "items", "correctOrder")),
    ("HotspotImage", ("imageUrl", "alt", "hotspots")),
    ("StepByStepReveal", ("title", "steps")),
    ("AudioExplanation", ("text", "voice")),
    ("PronunciationExercise", ("targetText", "language")),
    ("DiagramBuilder", ("title", "steps")),
    ("Accordion", ("children",)),
    ("AccordionItem", ("trigger", "children")),
)

# Explicitly out of the kit (§5.3), plus the names the spec renamed away from.
REJECTED_NAMES = (
    "Timeline",
    "ImageCard",
    "DragDrop",
    "Simulation",
    "SandboxHTML",
    "StepList",
    "BarChart",
    "LineChart",
)


def _spec(**overrides: object) -> dict:
    """A minimal valid spec: Stack root + lead + body."""
    payload: dict = {
        "version": "skillnet-ui/1",
        "format": "explanation",
        "root": "root",
        "components": [
            {"id": "root", "type": "Stack", "props": {"gap": "md"}, "children": ["a", "b"]},
            {"id": "a", "type": "TextContent", "props": {"text": "Guia.", "variant": "lead"}},
            {"id": "b", "type": "TextContent", "props": {"text": "Detalle.", "variant": "body"}},
        ],
    }
    payload.update(overrides)
    return payload


# -- the catalogue ------------------------------------------------------------------


def test_catalogue_is_the_frozen_list() -> None:
    assert UI_KIT.names == tuple(name for name, _ in EXPECTED_CATALOGUE)


@pytest.mark.parametrize(("name", "props"), EXPECTED_CATALOGUE)
def test_positional_prop_order_matches_the_spec_table(name: str, props: tuple[str, ...]) -> None:
    component = UI_KIT.get(name)
    assert component is not None
    assert component.prop_names == props


def test_only_markdown_is_off_limits_to_the_model() -> None:
    assert UI_KIT.llm_names == tuple(n for n, _ in EXPECTED_CATALOGUE if n != "Markdown")
    assert len(UI_KIT.llm_names) == 20


def test_containers_are_stack_and_card() -> None:
    assert UI_KIT.container_names == ("Stack", "Card", "Accordion", "AccordionItem")


def test_item_type_choices_are_the_existing_exercise_type_enum() -> None:
    quiz = UI_KIT.get("QuizItem")
    assert quiz is not None
    item_type = quiz.prop("item_type")
    assert item_type is not None
    assert item_type.choices == tuple(m.value for m in ExerciseType)
    assert len(item_type.choices) == 6


def test_each_container_declares_exactly_one_refs_prop() -> None:
    for component in UI_KIT.components:
        refs = [p for p in component.props if p.kind is PropKind.REFS]
        assert len(refs) == (1 if component.is_container else 0), component.name


# -- the names that stay out of the catalogue ----------------------------------------


@pytest.mark.parametrize("name", REJECTED_NAMES)
def test_a_rejected_name_is_not_in_the_kit(name: str) -> None:
    assert UI_KIT.get(name) is None


# -- the seven contract rules -------------------------------------------------------


def test_accepts_a_minimal_valid_spec() -> None:
    spec = parse_spec(_spec())
    assert spec.root == "root"
    assert len(spec.components) == 3


def test_rule_1_root_must_exist() -> None:
    with pytest.raises(RenderValidationError) as excinfo:
        parse_spec(_spec(root="nope"))
    assert any("rule 1" in e for e in excinfo.value.errors)


def test_rule_1_root_must_be_a_container() -> None:
    payload = _spec(root="a")
    with pytest.raises(RenderValidationError) as excinfo:
        parse_spec(payload)
    assert any("rule 1" in e for e in excinfo.value.errors)


def test_rule_2_dangling_reference_is_rejected() -> None:
    payload = _spec()
    payload["components"][0]["children"] = ["a", "ghost"]
    with pytest.raises(RenderValidationError) as excinfo:
        parse_spec(payload)
    assert any("rule 2" in e and "ghost" in e for e in excinfo.value.errors)


def test_rule_2_forward_references_are_allowed() -> None:
    payload = _spec()
    payload["components"].reverse()  # root now declared last
    assert parse_spec(payload).root == "root"


def test_rule_3_self_cycle_is_rejected() -> None:
    payload = _spec()
    payload["components"].append(
        {"id": "loop", "type": "Card", "props": {"title": "x"}, "children": ["loop"]}
    )
    payload["components"][0]["children"] = ["a", "loop"]
    with pytest.raises(RenderValidationError) as excinfo:
        parse_spec(payload)
    assert any("rule 3" in e for e in excinfo.value.errors)


def test_rule_3_two_cycle_is_rejected() -> None:
    payload = _spec()
    payload["components"][0]["children"] = ["a", "c1"]
    payload["components"] += [
        {"id": "c1", "type": "Card", "props": {"title": "1"}, "children": ["c2"]},
        {"id": "c2", "type": "Card", "props": {"title": "2"}, "children": ["c1"]},
    ]
    with pytest.raises(RenderValidationError) as excinfo:
        parse_spec(payload)
    assert any("rule 3" in e for e in excinfo.value.errors)


def test_rule_3_a_deep_dag_is_not_a_cycle() -> None:
    payload = _spec()
    payload["components"][0]["children"] = ["a", "c1"]
    payload["components"] += [
        {"id": "c1", "type": "Card", "props": {"title": "1"}, "children": ["c2", "b"]},
        {"id": "c2", "type": "Card", "props": {"title": "2"}, "children": ["b"]},
    ]
    assert len(parse_spec(payload).components) == 5


def test_rule_4_rejects_more_than_twelve_components() -> None:
    payload = _spec()
    payload["components"][0]["children"] = ["a"]
    for index in range(11):
        payload["components"].append(
            {
                "id": f"x{index}",
                "type": "TextContent",
                "props": {"text": f"Bloque {index}.", "variant": "body"},
            }
        )
    assert len(payload["components"]) == 14
    with pytest.raises(RenderValidationError) as excinfo:
        parse_spec(payload)
    assert any("rule 4" in e for e in excinfo.value.errors)


def test_rule_4_names_the_container_that_is_holding_the_list() -> None:
    """A bare count is a number the model can only obey by deleting the wrong thing.

    Measured on ``alergenos-hosteleria`` (2026-07-27): 19 blocks, 14 of them one-line
    ``TextContent``s inside one ``Card`` — a bullet list the kit has no component for.
    "got 19" pointed at none of that and the repair attempt was spent guessing.
    """
    payload = _spec()
    payload["components"][0]["children"] = ["a", "lista"]
    payload["components"].append(
        {
            "id": "lista",
            "type": "Card",
            "props": {"title": "Alergenos"},
            "children": [f"x{index}" for index in range(14)],
        }
    )
    for index in range(14):
        payload["components"].append(
            {
                "id": f"x{index}",
                "type": "TextContent",
                "props": {"text": f"Alergeno {index}.", "variant": "body"},
            }
        )
    with pytest.raises(RenderValidationError) as excinfo:
        parse_spec(payload)
    message = next(e for e in excinfo.value.errors if "rule 4" in e and "blocks" in e)
    assert "'lista' alone holds 14 of them" in message
    assert "A list of N items is ONE block" in message


def test_rule_4_does_not_name_a_culprit_when_the_blocks_are_spread_flat() -> None:
    """``devoluciones-tienda``, same run: 18 blocks, fullest container the root with 4.

    Naming the root there would be a guess, and the repair loop replays it verbatim.
    """
    payload = _spec()
    payload["components"][0]["children"] = ["a"]
    for index in range(16):
        payload["components"].append(
            {
                "id": f"x{index}",
                "type": "TextContent",
                "props": {"text": f"Bloque {index}.", "variant": "body"},
            }
        )
    with pytest.raises(RenderValidationError) as excinfo:
        parse_spec(payload)
    assert not any("alone holds" in e for e in excinfo.value.errors)


def test_a_sentence_in_an_enum_slot_is_reported_as_swapped_arguments() -> None:
    """``Callout`` is the only block whose enum comes first, and it is the only one the
    corpus has seen the arguments swapped on (``epi-taller``, 2026-07-27)."""
    payload = _spec()
    payload["components"][0]["children"] = ["a", "aviso"]
    payload["components"].append(
        {
            "id": "aviso",
            "type": "Callout",
            "props": {
                "tone": "Cuidado con el estado del EPI. Un EPI danado no protege.",
                "text": "warn",
            },
        }
    )
    with pytest.raises(RenderValidationError) as excinfo:
        parse_spec(payload)
    message = next(e for e in excinfo.value.errors if "aviso" in e)
    assert "the arguments are in the wrong order" in message
    assert "Callout(tone:" in message  # the real signature, so it can put them back


def test_a_near_miss_in_an_enum_slot_still_lists_the_choices() -> None:
    """``Callout("critical", ...)`` — the node's criticality used as a tone. Short, so it
    is a wrong choice and not a swap, and it must not be told to reorder anything."""
    payload = _spec()
    payload["components"][0]["children"] = ["a", "aviso"]
    payload["components"].append(
        {
            "id": "aviso",
            "type": "Callout",
            "props": {"tone": "critical", "text": "Un conato se apaga o se evacua."},
        }
    )
    with pytest.raises(RenderValidationError) as excinfo:
        parse_spec(payload)
    message = next(e for e in excinfo.value.errors if "aviso" in e)
    assert "must be one of: info, warn, success" in message
    assert "wrong order" not in message


def test_rule_4_rejects_more_than_five_root_children() -> None:
    payload = _spec()
    payload["components"][0]["children"] = ["a", "b", "x0", "x1", "x2", "x3"]
    for index in range(4):
        payload["components"].append(
            {
                "id": f"x{index}",
                "type": "TextContent",
                "props": {"text": f"Bloque {index}.", "variant": "body"},
            }
        )
    with pytest.raises(RenderValidationError) as excinfo:
        parse_spec(payload)
    assert any("rule 4" in e and "root level" in e for e in excinfo.value.errors)


def test_rule_4_accepts_exactly_twelve_components_and_five_at_root() -> None:
    payload = _spec()
    payload["components"][0]["children"] = ["a", "b", "x0", "x1", "x2"]
    for index in range(9):
        payload["components"].append(
            {
                "id": f"x{index}",
                "type": "TextContent",
                "props": {"text": f"Bloque {index}.", "variant": "body"},
            }
        )
    assert len(payload["components"]) == 12
    assert len(parse_spec(payload).components) == 12


# -- rule 4, the painting budget ------------------------------------------------------
#
# A DAG of 12 components expands to an unbounded TREE, because an id may be referenced
# from several parents and twice inside one children array, and only the root fan-out is
# capped. MEASURED with @openuidev/lang-core 0.2.10: the fan-out below at width 2 gives
# 1 025 elements from 334 bytes, at width 3 gives 29 526 from 370 bytes (all with
# ``statementCount == 12``, so the client's component check sees nothing wrong), and at
# width 8 a 550-byte program kills the tab with a V8 heap OOM after ~47 s. A heap OOM is
# not catchable, so the client cannot defend itself: this cap is the one that counts.


def _fan_out(width: int, depth: int) -> dict:
    """``a{i} = Card("n{i}", [a{i+1}] * width)``: 3 + depth components, width**depth leaves."""
    payload = _spec(format="explanation")
    payload["components"][0]["children"] = ["a", "n0"]
    payload["components"] = payload["components"][:2] + [
        {
            "id": f"n{index}",
            "type": "Card",
            "props": {"title": f"n{index}"},
            "children": [f"n{index + 1}"] * width,
        }
        for index in range(depth)
    ]
    payload["components"].append(
        {"id": f"n{depth}", "type": "TextContent", "props": {"text": "Hoja.", "variant": "body"}}
    )
    return payload


def test_rule_4_rejects_a_tree_that_expands_past_the_render_budget() -> None:
    payload = _fan_out(width=8, depth=9)
    assert len(payload["components"]) == 12  # rule 4's component count is satisfied
    with pytest.raises(RenderValidationError) as excinfo:
        parse_spec(payload)
    assert any("rule 4" in e and "64" in e for e in excinfo.value.errors)


def test_rule_4_rejects_the_same_id_repeated_inside_one_children_array() -> None:
    """The cheapest form of the same attack, and one no per-component rule can see."""
    payload = _spec()
    payload["components"][0]["children"] = ["a", "wide"]
    payload["components"].append(
        {"id": "wide", "type": "Card", "props": {"title": "W"}, "children": ["b"] * 70}
    )
    with pytest.raises(RenderValidationError) as excinfo:
        parse_spec(payload)
    assert any("rule 4" in e and "64" in e for e in excinfo.value.errors)


def test_rule_4_accepts_a_tree_right_at_the_render_budget() -> None:
    """Proof the cap is a cap and not a ban on reuse: 64 painted blocks is fine."""
    payload = _spec()
    payload["components"][0]["children"] = ["a", "wide"]
    payload["components"].append(
        # root + lead + Card + 61 references to `b` = 64 elements.
        {"id": "wide", "type": "Card", "props": {"title": "W"}, "children": ["b"] * 61}
    )
    assert len(parse_spec(payload).components) == 4


def test_rule_4_reports_a_cycle_instead_of_looping_on_the_expansion() -> None:
    """The expansion is only defined on a DAG; rule 3 has to win, not hang."""
    payload = _spec()
    payload["components"][0]["children"] = ["a", "c1"]
    payload["components"] += [
        {"id": "c1", "type": "Card", "props": {"title": "1"}, "children": ["c2"] * 9},
        {"id": "c2", "type": "Card", "props": {"title": "2"}, "children": ["c1"] * 9},
    ]
    with pytest.raises(RenderValidationError) as excinfo:
        parse_spec(payload)
    assert any("rule 3" in e for e in excinfo.value.errors)


def test_the_render_budget_is_not_checked_in_partial_mode() -> None:
    """Mid-stream a spec is legitimately half-built; rules 1-4 and 7 do not run."""
    parse_spec(_fan_out(width=8, depth=9), partial=True)


@pytest.mark.parametrize("key", ("correct", "explanation", "correct_order", "blanks"))
def test_rule_5_quiz_item_never_carries_the_answer(key: str) -> None:
    payload = _spec(format="exercise")
    payload["components"][0]["children"] = ["q"]
    payload["components"] = [payload["components"][0]] + [
        {
            "id": "q",
            "type": "QuizItem",
            "props": {
                "item_id": "q1",
                "item_type": "test",
                "bloom_level": "apply",
                "question": "Que haces?",
                "options": ["A", "B"],
                key: 1,
            },
        }
    ]
    with pytest.raises(RenderValidationError) as excinfo:
        parse_spec(payload)
    assert any("rule 5" in e for e in excinfo.value.errors)


def test_rule_6_rejects_html_in_text() -> None:
    payload = _spec()
    payload["components"][1]["props"]["text"] = "Lee <b>esto</b> con atencion."
    with pytest.raises(RenderValidationError) as excinfo:
        parse_spec(payload)
    assert any("rule 6" in e for e in excinfo.value.errors)


def test_rule_6_allows_inline_markup_and_a_bare_less_than() -> None:
    payload = _spec()
    payload["components"][1]["props"]["text"] = (
        "Si el plazo es **menor** que 30 dias (dias < 30) usa `devolucion`."
    )
    assert parse_spec(payload) is not None


@pytest.mark.parametrize("ui_format", ("explanation", "mixed"))
def test_rule_7_requires_a_lead_or_callout_first(ui_format: str) -> None:
    payload = _spec(format=ui_format)
    payload["components"][1]["props"]["variant"] = "body"
    with pytest.raises(RenderValidationError) as excinfo:
        parse_spec(payload)
    assert any("rule 7" in e for e in excinfo.value.errors)


def test_rule_7_is_satisfied_by_a_callout() -> None:
    payload = _spec()
    payload["components"][1] = {
        "id": "a",
        "type": "Callout",
        "props": {"tone": "info", "text": "Para que te sirve: cobrar bien."},
    }
    assert parse_spec(payload) is not None


@pytest.mark.parametrize("ui_format", ("exercise", "chart"))
def test_rule_7_does_not_apply_to_the_other_formats(ui_format: str) -> None:
    payload = _spec(format=ui_format)
    payload["components"][1]["props"]["variant"] = "body"
    assert parse_spec(payload) is not None


# -- component-level validation -----------------------------------------------------


def test_unknown_component_type_is_rejected() -> None:
    payload = _spec()
    payload["components"][1]["type"] = "Timeline"
    with pytest.raises(RenderValidationError) as excinfo:
        parse_spec(payload)
    assert any("unknown component type" in e for e in excinfo.value.errors)


def test_missing_prop_is_rejected() -> None:
    payload = _spec()
    del payload["components"][1]["props"]["variant"]
    with pytest.raises(RenderValidationError) as excinfo:
        parse_spec(payload)
    assert any("missing prop 'variant'" in e for e in excinfo.value.errors)


def test_enum_prop_rejects_a_value_outside_the_kit() -> None:
    payload = _spec()
    payload["components"][0]["props"]["gap"] = "xl"
    with pytest.raises(RenderValidationError) as excinfo:
        parse_spec(payload)
    assert any("prop 'gap'" in e for e in excinfo.value.errors)


def test_table_rows_must_be_nested_arrays() -> None:
    payload = _spec()
    payload["components"][2] = {
        "id": "b",
        "type": "Table",
        "props": {"headers": ["A", "B"], "rows": ["1", "2"]},
    }
    with pytest.raises(RenderValidationError) as excinfo:
        parse_spec(payload)
    assert any("array of arrays" in e for e in excinfo.value.errors)


def test_chart_values_must_be_numbers() -> None:
    payload = _spec(format="chart")
    payload["components"][2] = {
        "id": "b",
        "type": "Chart",
        "props": {"kind": "line", "title": "T", "labels": ["a"], "values": ["1"]},
    }
    with pytest.raises(RenderValidationError) as excinfo:
        parse_spec(payload)
    assert any("array of numbers" in e for e in excinfo.value.errors)


def test_non_container_cannot_take_children() -> None:
    payload = _spec()
    payload["components"][1]["children"] = ["b"]
    with pytest.raises(RenderValidationError) as excinfo:
        parse_spec(payload)
    assert any("takes no children" in e for e in excinfo.value.errors)


def test_duplicate_ids_are_rejected() -> None:
    payload = _spec()
    payload["components"][2]["id"] = "a"
    with pytest.raises(RenderValidationError) as excinfo:
        parse_spec(payload)
    assert any("duplicate component id" in e for e in excinfo.value.errors)


def test_unknown_version_is_rejected() -> None:
    with pytest.raises(RenderValidationError):
        parse_spec(_spec(version="skillnet-ui/2"))


def test_unknown_format_is_rejected() -> None:
    with pytest.raises(RenderValidationError):
        parse_spec(_spec(format="carousel"))


def test_partial_mode_tolerates_dangling_refs_and_no_lead() -> None:
    payload = {
        "version": "skillnet-ui/1",
        "format": "explanation",
        "root": "root",
        "components": [
            {"id": "root", "type": "Stack", "props": {"gap": "md"}, "children": ["a", "b"]}
        ],
    }
    spec = parse_spec(payload, partial=True)
    assert spec.components[0].children == ["a", "b"]


def test_partial_mode_still_rejects_an_unknown_component() -> None:
    payload = {
        "version": "skillnet-ui/1",
        "format": "explanation",
        "root": "root",
        "components": [{"id": "root", "type": "Nope", "props": {}}],
    }
    with pytest.raises(RenderValidationError):
        parse_spec(payload, partial=True)
