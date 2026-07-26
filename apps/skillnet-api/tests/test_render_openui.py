"""The ``openui`` dialect: golden parses, the malformed set, and streaming truncation.

No DB, no network. The dialect fixtures live in ``tests/fixtures/dsl/*.openui`` and
their expected IR in ``tests/fixtures/ui-specs/*.json`` — the same JSON files the
frontend renders (§12.3), so a contract break fails both sides at once.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from src.render import RenderError, RenderParseError, UISpec, get_render_backend
from src.render.backends.openui import GRAMMAR, OpenUiLangBackend, infer_format

BACKEND = OpenUiLangBackend()

_DSL_DIR = pathlib.Path(__file__).parent / "fixtures" / "dsl"
_SPEC_DIR = pathlib.Path(__file__).parent / "fixtures" / "ui-specs"

VALID = (
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

# One fixture per failure mode. The first three are the three frozen grammar rules
# of §5.4, in order.
MALFORMED = (
    "malformed_unescaped_quote",  # rule 1
    "malformed_flat_table_rows",  # rule 2
    "malformed_literal_newline",  # rule 3
    "malformed_unclosed_array",
    "malformed_missing_assign",
    "invalid_unknown_component",
)


def _dsl(name: str) -> str:
    return (_DSL_DIR / f"{name}.openui").read_text(encoding="utf-8")


def _golden(name: str) -> dict:
    return json.loads((_SPEC_DIR / f"{name}.json").read_text(encoding="utf-8"))


def test_there_are_at_least_eight_valid_dialects_and_six_malformed() -> None:
    assert len(VALID) >= 8
    assert len(MALFORMED) == 6
    assert len(set(VALID) | set(MALFORMED)) == len(VALID) + len(MALFORMED)


# -- valid dialects -----------------------------------------------------------------


@pytest.mark.parametrize("name", VALID)
def test_parse_matches_the_golden_spec(name: str) -> None:
    spec = BACKEND.parse(_dsl(name))
    assert spec.model_dump(mode="json") == _golden(name)


@pytest.mark.parametrize("name", VALID)
def test_every_golden_is_a_valid_ui_spec(name: str) -> None:
    spec = UISpec.model_validate(_golden(name))
    assert spec.version == "skillnet-ui/1"
    assert spec.component(spec.root) is not None


def test_escapes_decode_to_real_characters() -> None:
    spec = BACKEND.parse(_dsl("escapes"))
    intro = spec.component("intro")
    cita = spec.component("cita")
    assert intro is not None and cita is not None
    assert '"' in intro.props["text"]
    assert "\\" in intro.props["text"]
    assert "\n" in cita.props["text"]
    # Rule 3: the literal source carries no line break inside the quotes.
    assert len(_dsl("escapes").rstrip("\n").split("\n")) == 3


def test_code_block_keeps_its_newlines_as_escapes() -> None:
    spec = BACKEND.parse(_dsl("card_nested"))
    codigo = spec.component("codigo")
    assert codigo is not None
    assert codigo.props["code"].count("\n") == 2


def test_nested_table_rows_are_a_matrix() -> None:
    spec = BACKEND.parse(_dsl("table_nested"))
    tabla = spec.component("tabla")
    assert tabla is not None
    assert tabla.props["rows"] == [
        ["Tienda", "30 dias", "0 EUR"],
        ["Web", "14 dias", "3,95 EUR"],
        ["Telefono", "14 dias", "0 EUR"],
    ]


def test_numbers_keep_their_type_and_sign() -> None:
    spec = BACKEND.parse(_dsl("chart_data"))
    grafico = spec.component("grafico")
    assert grafico is not None
    assert grafico.props["values"] == [12, 8.5, -3]


def test_forward_references_and_loose_whitespace_are_accepted() -> None:
    spec = BACKEND.parse(_dsl("deep_stack"))
    assert spec.root == "root"
    assert spec.component("grupo") is not None


def test_code_fences_and_blank_lines_are_ignored() -> None:
    raw = _dsl("quiz_types")
    assert raw.lstrip().startswith("```")
    assert "\n\n" in raw
    assert len(BACKEND.parse(raw).components) == 5


def test_root_is_the_component_nobody_references() -> None:
    spec = BACKEND.parse(
        'contenedor = Stack([intro], "md")\n'
        'intro = TextContent("Para que te sirve: cobrar bien.", "lead")\n'
    )
    assert spec.root == "contenedor"


def test_empty_arrays_are_legal() -> None:
    spec = BACKEND.parse(_dsl("exercise_only"))
    q1 = spec.component("q1")
    assert q1 is not None
    assert q1.props["options"] == []


# -- format recovery ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    (
        ("explanation_basic", "explanation"),
        ("mixed_quiz", "mixed"),
        ("exercise_only", "exercise"),
        ("chart_data", "chart"),
    ),
)
def test_format_is_inferred_from_the_component_mix(name: str, expected: str) -> None:
    assert BACKEND.parse(_dsl(name)).format == expected
    assert infer_format(BACKEND.parse(_dsl(name)).components) == expected


def test_an_explicit_format_wins_over_inference() -> None:
    # What the runtime does: decide_formato already chose, so it is passed in.
    spec = BACKEND.parse(_dsl("chart_data"), ui_format="mixed")
    assert spec.format == "mixed"


def test_an_explicit_format_still_enforces_rule_7() -> None:
    raw = 'root = Stack([a], "md")\na = TextContent("Sin lead.", "body")\n'
    with pytest.raises(RenderParseError) as excinfo:
        BACKEND.parse(raw, ui_format="explanation")
    assert any("rule 7" in e for e in excinfo.value.errors)


# -- malformed dialects -------------------------------------------------------------


@pytest.mark.parametrize("name", MALFORMED)
def test_malformed_dialect_raises_render_parse_error(name: str) -> None:
    with pytest.raises(RenderParseError):
        BACKEND.parse(_dsl(name))


@pytest.mark.parametrize("name", MALFORMED)
def test_the_error_carries_the_messages_the_repair_prompt_needs(name: str) -> None:
    with pytest.raises(RenderParseError) as excinfo:
        BACKEND.parse(_dsl(name))
    assert excinfo.value.errors
    assert all(isinstance(message, str) and message for message in excinfo.value.errors)


def test_grammar_rule_1_unescaped_quote() -> None:
    with pytest.raises(RenderParseError) as excinfo:
        BACKEND.parse(_dsl("malformed_unescaped_quote"))
    assert "line 2" in str(excinfo.value)
    assert 'written \\"' in str(excinfo.value)


def test_grammar_rule_1_an_escaped_quote_is_fine() -> None:
    raw = 'root = Stack([a], "md")\na = TextContent("Dijo \\"hola\\" ayer.", "lead")\n'
    component = BACKEND.parse(raw).component("a")
    assert component is not None
    assert component.props["text"] == 'Dijo "hola" ayer.'


def test_grammar_rule_2_table_rows_must_be_nested() -> None:
    with pytest.raises(RenderParseError) as excinfo:
        BACKEND.parse(_dsl("malformed_flat_table_rows"))
    assert "array of arrays" in str(excinfo.value)


def test_grammar_rule_3_a_literal_newline_breaks_the_string() -> None:
    with pytest.raises(RenderParseError) as excinfo:
        BACKEND.parse(_dsl("malformed_literal_newline"))
    assert "unterminated text value" in str(excinfo.value)


def test_grammar_rule_3_the_escape_form_is_accepted() -> None:
    raw = 'root = Stack([a], "md")\na = TextContent("Uno.\\nDos.", "lead")\n'
    component = BACKEND.parse(raw).component("a")
    assert component is not None
    assert component.props["text"] == "Uno.\nDos."


def test_wrong_arity_is_rejected() -> None:
    with pytest.raises(RenderParseError) as excinfo:
        BACKEND.parse('root = Stack([a])\na = TextContent("Hola.", "lead")\n')
    assert "positional arguments" in str(excinfo.value)


def test_quoted_child_ids_are_rejected() -> None:
    with pytest.raises(RenderParseError) as excinfo:
        BACKEND.parse('root = Stack(["a"], "md")\na = TextContent("Hola.", "lead")\n')
    assert "array of component ids" in str(excinfo.value)


def test_an_invalid_escape_is_rejected() -> None:
    with pytest.raises(RenderParseError) as excinfo:
        BACKEND.parse('root = Stack([a], "md")\na = TextContent("Tab\\there.", "lead")\n')
    assert "invalid escape" in str(excinfo.value)


def test_trailing_text_after_the_call_is_rejected() -> None:
    with pytest.raises(RenderParseError) as excinfo:
        BACKEND.parse('root = Stack([a], "md") y algo mas\n')
    assert "trailing text" in str(excinfo.value)


def test_the_model_cannot_emit_markdown() -> None:
    with pytest.raises(RenderParseError) as excinfo:
        BACKEND.parse('root = Stack([m], "md")\nm = Markdown("# Hola")\n')
    assert "unknown component 'Markdown'" in str(excinfo.value)


def test_an_empty_program_is_rejected() -> None:
    with pytest.raises(RenderParseError):
        BACKEND.parse("```openui\n```\n")


def test_a_trailing_comma_is_rejected() -> None:
    with pytest.raises(RenderParseError) as excinfo:
        BACKEND.parse('root = Stack([a,], "md")\na = TextContent("Hola.", "lead")\n')
    assert "trailing comma" in str(excinfo.value)


# -- parse_partial: streaming --------------------------------------------------------

_SWEEP_FIXTURES = ("explanation_basic", "escapes", "mixed_quiz")
_SWEEP = [
    (name, cut)
    for name in _SWEEP_FIXTURES
    for cut in range(len(_dsl(name)) + 1)
]
_FULL_IDS = {name: [c.id for c in BACKEND.parse(_dsl(name)).components] for name in _SWEEP_FIXTURES}


@pytest.mark.parametrize(("name", "cut"), _SWEEP)
def test_parse_partial_never_raises_at_any_truncation(name: str, cut: int) -> None:
    """Every byte offset of a stream, not a random sample (and no new dependency)."""
    prefix = _dsl(name)[:cut]
    spec = BACKEND.parse_partial(prefix)
    assert isinstance(spec, UISpec)
    assert spec.version == "skillnet-ui/1"
    ids = [component.id for component in spec.components]
    assert len(ids) == len(set(ids))
    # One component per line in these fixtures, so a completed line is a completed
    # component and nothing beyond the last newline may leak in.
    assert ids == _FULL_IDS[name][: prefix.count("\n")]


def test_parse_partial_drops_the_half_written_last_line() -> None:
    raw = _dsl("explanation_basic")
    cut = raw.index("\n") + 1 + 20  # first line plus 20 bytes of the second
    spec = BACKEND.parse_partial(raw[:cut])
    assert [c.id for c in spec.components] == ["root"]


def test_parse_partial_keeps_a_complete_last_line() -> None:
    raw = _dsl("explanation_basic")
    cut = raw.index("\n") + 1
    assert len(BACKEND.parse_partial(raw[:cut]).components) == 1


def test_parse_partial_tolerates_dangling_forward_references() -> None:
    spec = BACKEND.parse_partial('root = Stack([intro, quiz], "md")\n')
    assert spec.components[0].children == ["intro", "quiz"]
    assert spec.root == "root"


def test_parse_partial_on_empty_input_is_an_empty_spec() -> None:
    spec = BACKEND.parse_partial("")
    assert spec.components == []
    assert spec.root == ""


@pytest.mark.parametrize("name", MALFORMED)
def test_parse_partial_never_raises_on_malformed_input(name: str) -> None:
    spec = BACKEND.parse_partial(_dsl(name))
    assert isinstance(spec, UISpec)


def test_parse_partial_skips_the_broken_line_and_keeps_the_rest() -> None:
    raw = (
        'root = Stack([a, b], "md")\n'
        'a = TextContent("roto porque falta la coma" "lead")\n'
        'b = TextContent("Este si vale.", "body")\n'
    )
    ids = [c.id for c in BACKEND.parse_partial(raw).components]
    assert ids == ["root", "b"]


def test_parse_partial_lets_a_retransmitted_line_win() -> None:
    raw = (
        'root = Stack([a], "md")\n'
        'a = TextContent("Primera version.", "lead")\n'
        'a = TextContent("Segunda version.", "lead")\n'
    )
    spec = BACKEND.parse_partial(raw)
    component = spec.component("a")
    assert component is not None
    assert component.props["text"] == "Segunda version."
    assert len(spec.components) == 2


# -- the registry -------------------------------------------------------------------


def test_the_default_backend_is_openui() -> None:
    assert get_render_backend().name == "openui"
    assert get_render_backend("openui") is get_render_backend()


def test_an_unknown_backend_is_a_render_error() -> None:
    with pytest.raises(RenderError):
        get_render_backend("a2tl")


def test_the_frozen_grammar_lists_exactly_the_nine_emittable_components() -> None:
    production = GRAMMAR.split("comp_name  =", 1)[1].split(";", 1)[0]
    names = {token.strip('"') for token in production.replace("|", " ").split() if token.strip('"')}
    assert names == {
        "Stack",
        "TextContent",
        "Card",
        "Callout",
        "StepSequence",
        "Table",
        "CodeBlock",
        "Chart",
        "QuizItem",
    }
    assert "Markdown" not in GRAMMAR
