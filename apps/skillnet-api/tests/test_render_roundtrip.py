"""``parse(serialize(spec)) == spec`` over the golden specs (§12.2).

No DB, no network. ``serialize`` is the inverse of ``parse`` over the nine emittable
components; ``Markdown`` only ever reaches a spec through ``fallback_seed``, which
builds JSON directly, so it is the one golden that is not round-trippable — and the
test asserts that asymmetry instead of hiding it.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from src.render import RenderError, UISpec
from src.render.backends.openui import OpenUiLangBackend

BACKEND = OpenUiLangBackend()

_SPEC_DIR = pathlib.Path(__file__).parent / "fixtures" / "ui-specs"

#: Golden specs that the dialect can express. Ten, per §12.2.
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
)

#: Golden specs the dialect deliberately cannot express.
JSON_ONLY = ("fallback_markdown",)


def _spec(name: str) -> UISpec:
    return UISpec.model_validate(
        json.loads((_SPEC_DIR / f"{name}.json").read_text(encoding="utf-8"))
    )


def test_the_golden_set_is_ten_round_trippable_specs() -> None:
    on_disk = {path.stem for path in _SPEC_DIR.glob("*.json")}
    assert len(ROUND_TRIPPABLE) == 10
    assert on_disk == set(ROUND_TRIPPABLE) | set(JSON_ONLY)


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


@pytest.mark.parametrize("name", JSON_ONLY)
def test_a_markdown_spec_is_valid_ir_but_not_serializable(name: str) -> None:
    spec = _spec(name)
    assert "Markdown" in spec.types
    with pytest.raises(RenderError) as excinfo:
        BACKEND.serialize(spec)
    assert "fallback_seed" in str(excinfo.value)
