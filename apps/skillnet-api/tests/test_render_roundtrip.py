"""``parse(serialize(spec)) == spec`` over the golden specs (§12.2).

No DB, no network. ``serialize`` is the inverse of ``parse`` over the nine emittable
components. ``Markdown`` is the one golden that does not round-trip: the server authors
it for ``fallback_seed`` and ``serialize`` writes it (the browser is served dialect now,
so the fallback needs a dialect form), but ``parse`` refuses it because the model may not
emit it. The test asserts that asymmetry instead of hiding it.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from src.render import RenderError, UISpec
from src.render.backends.openui import OpenUiLangBackend

BACKEND = OpenUiLangBackend()

_SPEC_DIR = pathlib.Path(__file__).parent / "fixtures" / "ui-specs"

#: Golden specs that the dialect can express. Ten of §12.2 plus ``inline_nested``, which
#: is the eleventh because the inline form parses to a spec like any other — and its
#: golden file is where the synthetic ids are pinned.
ROUND_TRIPPABLE = (
    "explanation_basic",
    "explanation_callout_first",
    "mixed_quiz",
    "exercise_only",
    "chart_data",
    "table_nested",
    "card_nested",
    "escapes",
    "deep_stack",
    "quiz_types",
    "inline_nested",
)

#: Golden specs only the server authors: the dialect can write them, the model cannot.
SERVER_AUTHORED = ("fallback_markdown",)


def _spec(name: str) -> UISpec:
    return UISpec.model_validate(
        json.loads((_SPEC_DIR / f"{name}.json").read_text(encoding="utf-8"))
    )


def test_the_golden_set_is_eleven_round_trippable_specs() -> None:
    on_disk = {path.stem for path in _SPEC_DIR.glob("*.json")}
    assert len(ROUND_TRIPPABLE) == 11
    assert on_disk == set(ROUND_TRIPPABLE) | set(SERVER_AUTHORED)


@pytest.mark.parametrize("name", ROUND_TRIPPABLE)
def test_parse_of_serialize_is_the_identity(name: str) -> None:
    spec = _spec(name)
    assert BACKEND.parse(BACKEND.serialize(spec)) == spec


@pytest.mark.parametrize("name", ROUND_TRIPPABLE)
def test_serialize_is_stable(name: str) -> None:
    spec = _spec(name)
    once = BACKEND.serialize(spec)
    assert BACKEND.serialize(BACKEND.parse(once)) == once


@pytest.mark.parametrize("name", ROUND_TRIPPABLE)
def test_serialize_emits_one_line_per_component(name: str) -> None:
    spec = _spec(name)
    text = BACKEND.serialize(spec)
    assert text.endswith("\n")
    assert len(text.rstrip("\n").split("\n")) == len(spec.components)


# -- the shapes §12.2 demands the round trip covers ----------------------------------


def test_the_golden_set_covers_a_quiz_item() -> None:
    names = [n for n in ROUND_TRIPPABLE if "QuizItem" in _spec(n).types]
    assert names
    spec = _spec("mixed_quiz")
    quiz = spec.component("quiz")
    assert quiz is not None
    assert quiz.props["item_type"] == "test"
    assert BACKEND.parse(BACKEND.serialize(spec)).component("quiz") == quiz


def test_the_golden_set_covers_a_nested_stack() -> None:
    spec = _spec("deep_stack")
    outer = spec.component("root")
    inner = spec.component("grupo")
    assert outer is not None and inner is not None
    assert inner.id in outer.children
    assert inner.type == "Stack"
    assert BACKEND.parse(BACKEND.serialize(spec)) == spec


def test_the_golden_set_covers_a_table_with_nested_rows() -> None:
    spec = _spec("table_nested")
    tabla = spec.component("tabla")
    assert tabla is not None
    assert all(isinstance(row, list) for row in tabla.props["rows"])
    reparsed = BACKEND.parse(BACKEND.serialize(spec)).component("tabla")
    assert reparsed is not None
    assert reparsed.props["rows"] == tabla.props["rows"]


def test_the_canonical_form_of_an_inline_program_is_the_referenced_one() -> None:
    """`serialize` has one output per spec, and the inline form is not it (§5.4).

    Both spellings parse to the same shape, so only one of them can be the text the
    browser is served — and the flat one is what their prompt recommends for streaming
    and the only one that gives every block a real statement id in their parser.
    """
    inline = pathlib.Path(__file__).parent / "fixtures" / "dsl" / "inline_nested.openui"
    spec = BACKEND.parse(inline.read_text(encoding="utf-8"))
    program = BACKEND.serialize(spec)
    assert spec == _spec("inline_nested")
    assert len(program.rstrip("\n").split("\n")) == len(spec.components)
    for line in program.rstrip("\n").split("\n"):
        assert line.count("(") == 1, f"a serialized line is one call: {line}"
    assert BACKEND.parse(program) == spec


def test_the_golden_set_covers_a_nested_card() -> None:
    spec = _spec("card_nested")
    ficha = spec.component("ficha")
    assert ficha is not None
    assert ficha.type == "Card"
    assert len(ficha.children) == 2


# -- escaping ------------------------------------------------------------------------


def test_serialize_applies_the_three_escape_rules() -> None:
    spec = _spec("escapes")
    text = BACKEND.serialize(spec)
    assert '\\"' in text  # rule 1
    assert "\\\\" in text  # a literal backslash
    assert "\\n" in text  # rule 3
    # No raw line break survives inside a quoted value: one component per line.
    assert len(text.rstrip("\n").split("\n")) == len(spec.components)
    assert BACKEND.parse(text) == spec


def test_a_carriage_return_is_normalised_to_an_escape() -> None:
    spec = UISpec.model_validate(
        {
            "version": "skillnet-ui/1",
            "format": "explanation",
            "root": "root",
            "components": [
                {"id": "root", "type": "Stack", "props": {"gap": "md"}, "children": ["a"]},
                {
                    "id": "a",
                    "type": "TextContent",
                    "props": {"text": "Uno.\r\nDos.", "variant": "lead"},
                },
            ],
        }
    )
    text = BACKEND.serialize(spec)
    assert "\r" not in text
    assert len(text.rstrip("\n").split("\n")) == 2
    reparsed = BACKEND.parse(text).component("a")
    assert reparsed is not None
    assert reparsed.props["text"] == "Uno.\nDos."


def test_nested_quotes_in_a_table_cell_survive() -> None:
    spec = UISpec.model_validate(
        {
            "version": "skillnet-ui/1",
            "format": "explanation",
            "root": "root",
            "components": [
                {"id": "root", "type": "Stack", "props": {"gap": "md"}, "children": ["a", "t"]},
                {
                    "id": "a",
                    "type": "TextContent",
                    "props": {"text": "Compara.", "variant": "lead"},
                },
                {
                    "id": "t",
                    "type": "Table",
                    "props": {
                        "headers": ['El "plazo"', "Accion"],
                        "rows": [['30 dias, sin "peros"', "Devolucion"]],
                    },
                },
            ],
        }
    )
    assert BACKEND.parse(BACKEND.serialize(spec)) == spec


# -- the deliberate asymmetry --------------------------------------------------------


@pytest.mark.parametrize("name", SERVER_AUTHORED)
def test_a_markdown_spec_serializes_but_cannot_be_parsed_back(name: str) -> None:
    """The asymmetry moved, it did not disappear.

    It used to be "``Markdown`` has no dialect form": the browser received JSON, so
    ``fallback_seed`` never needed one. Now the browser is served dialect, so the fallback
    is serialized like everything else — while ``parse`` still refuses ``Markdown``,
    because the *model* may not emit it. Server writes it, model cannot.
    """
    spec = _spec(name)
    assert "Markdown" in spec.types
    program = BACKEND.serialize(spec)
    assert "Markdown(" in program
    with pytest.raises(RenderError) as excinfo:
        BACKEND.parse(program)
    assert "unknown component 'Markdown'" in str(excinfo.value)


# -- accented ids reach a fixed point in one step ---------------------------------------
#
# `parse` folds a non-ASCII id to ASCII (`src/render/backends/openui.py`), so the accented
# program and its folded form are the same spec, and re-parsing the canonical text changes
# nothing. That second property is the one that matters: the canonical text is what is
# persisted and what the browser tokenizes, and `canonicalize` asserts over it a second
# time on the way out.


def test_an_accented_program_and_its_folded_form_are_the_same_spec() -> None:
    accented = (
        'root = Stack([introduccion, conclusión], "md")\n'
        'introduccion = TextContent("Hola.", "lead")\n'
        'conclusión = TextContent("Adiós, con tilde en el texto.", "body")\n'
    )
    folded = accented.replace("conclusión", "conclusion")
    assert BACKEND.parse(accented) == BACKEND.parse(folded)


def test_serializing_an_accented_program_is_a_fixed_point() -> None:
    accented = (
        'root = Stack([conclusión], "md")\n'
        'conclusión = TextContent("Adiós.", "lead")\n'
    )
    once = BACKEND.serialize(BACKEND.parse(accented))
    # The *ids* are ASCII, which is all lang-core's tokenizer needs; a string literal may
    # hold anything, because their scanner takes it whole and JSON.parses it.
    assert once.split(" =")[0].isascii()
    assert all(line.split(" =")[0].isascii() for line in once.splitlines())
    assert BACKEND.serialize(BACKEND.parse(once)) == once
    # The learner-visible text keeps its accents; only the id was ever folded.
    assert "Adiós." in BACKEND.parse(once).component("conclusion").props["text"]
