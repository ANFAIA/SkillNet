"""A model that answers in almost-JSON must not cost a whole course generation.

Two failures, one cause, both fixed here. The v1 pipeline makes five JSON calls
(themes, structure, modules, review, refinement) and every one of them asks for a JSON
*object*. Neither enforced JSON mode delivers that: litellm maps
``json_mode=True`` to ollama's ``format: "json"`` and to OpenAI's
``response_format: {"type": "json_object"}`` (verified on litellm 1.91.3), and both
guarantee **syntax only** — never the schema, and on providers where the flag is
advisory, not even the syntax.

So two things arrive that used to be fatal:

1. **Chain of thought in the content field.** ``design_structure`` died on it: the
   thinking restates the requested shape, the shape sketches in
   ``src/llm/prompts/generation.py`` are full of braces, and the old parser locked onto
   the *first* balanced ``{...}`` — a fragment of the reasoning — then gave up.
2. **The wrapper object dropped.** A bare ``[...]`` where a dict was expected, which
   reached ``generate_modules`` as ``'list' object has no attribute 'get'``.

No test here touches the database, the network or a provider key.
"""

from __future__ import annotations

import json
import logging

import pytest

from src.agents.content.helpers import (
    module_payload,
    outline_dict,
    review_report,
    themes_list,
)
from src.core.exceptions import LLMError
from src.llm.parsing import (
    PARSE_FAILED,
    RAW_PREVIEW_CHARS,
    parse_json_response,
    strip_reasoning,
)

# The shape sketch the structure designer's system prompt contains, restated by the
# model while it thinks. `str` is not JSON and `[...]` is not JSON, which is exactly why
# the old balanced-brace scan came away with nothing.
THINKING_ABOUT_THE_SHAPE = (
    "Tengo que devolver "
    '{"title": str, "description": str, "outcome": str, "modules": [...]} '
    "y son 2 temas, asi que hare 2 modulos."
)
OUTLINE_JSON = (
    '{"title": "Higiene alimentaria", "description": "d", "outcome": "o", '
    '"modules": [{"title": "M1", "summary": "s", "position": 1}]}'
)


# --------------------------------------------------------------------------- #
# strip_reasoning
# --------------------------------------------------------------------------- #
def test_a_think_wrapped_object_parses() -> None:
    raw = f"<think>\n{THINKING_ABOUT_THE_SHAPE}\n</think>\n{OUTLINE_JSON}"
    parsed = parse_json_response(raw)
    assert parsed["title"] == "Higiene alimentaria"
    assert parsed["modules"][0]["title"] == "M1"


@pytest.mark.parametrize("tag", ["think", "thinking", "reasoning", "reflection"])
def test_every_reasoning_tag_spelling_is_stripped(tag: str) -> None:
    raw = f"<{tag}>{THINKING_ABOUT_THE_SHAPE}</{tag}>{OUTLINE_JSON}"
    assert parse_json_response(raw)["title"] == "Higiene alimentaria"


def test_an_open_tag_with_attributes_is_stripped() -> None:
    raw = f'<think type="internal">{THINKING_ABOUT_THE_SHAPE}</think >{OUTLINE_JSON}'
    assert parse_json_response(raw)["outcome"] == "o"


def test_a_stray_closing_tag_drops_everything_before_it() -> None:
    """Chat templates that inject the opening tag themselves never echo it back, so the
    response starts mid-thought and the only marker is the closer."""
    raw = f"{THINKING_ABOUT_THE_SHAPE}</think>{OUTLINE_JSON}"
    assert parse_json_response(raw)["description"] == "d"


def test_an_unterminated_think_block_is_reported_as_reasoning_only() -> None:
    """The budget ran out mid-thought: there is no answer in there at all, and saying so
    is worth more than "invalid JSON"."""
    raw = f'<think>\n{THINKING_ABOUT_THE_SHAPE}\nEmpiezo: {{"title": "Higiene"'
    with pytest.raises(LLMError) as excinfo:
        parse_json_response(raw)
    message = str(excinfo.value)
    assert "cut off mid-thought" in message
    assert "Tengo que devolver" in message  # the raw response travels with the error


def test_thinking_then_an_answer_then_more_thinking() -> None:
    raw = f"<think>a</think>{OUTLINE_JSON}<think>ahora reviso si"
    assert parse_json_response(raw)["title"] == "Higiene alimentaria"


def test_a_think_tag_inside_a_json_string_is_not_stripped() -> None:
    """A lesson about prompting may legitimately contain the text ``<think>``. Valid JSON
    is returned before any stripping happens, so the payload is never rewritten."""
    payload = {"lessons": [{"title": "Prompting", "content": "Escribe <think> y luego"}]}
    parsed = parse_json_response(json.dumps(payload))
    assert parsed == payload


def test_strip_reasoning_leaves_an_ordinary_response_alone() -> None:
    assert strip_reasoning(f"  {OUTLINE_JSON}  ") == OUTLINE_JSON


# --------------------------------------------------------------------------- #
# candidate spans: the first balanced span is not necessarily the answer
# --------------------------------------------------------------------------- #
def test_prose_with_braces_before_the_json() -> None:
    raw = (
        "Claro. El formato pedido era {clave: valor} pero aqui va el resultado:\n"
        f"{OUTLINE_JSON}"
    )
    assert parse_json_response(raw)["title"] == "Higiene alimentaria"


def test_a_parseable_prose_example_does_not_beat_the_payload() -> None:
    """The earlier span parses perfectly and is still the wrong answer. Longest wins."""
    raw = f'Por ejemplo {{"title": "Ejemplo"}}. El curso:\n{OUTLINE_JSON}'
    assert parse_json_response(raw)["title"] == "Higiene alimentaria"


def test_a_bare_list_is_not_reduced_to_its_first_element() -> None:
    """Every element of a bare array is itself a balanced ``{...}`` that parses. Taking
    objects before arrays would silently return one module out of three."""
    raw = 'Aqui tienes:\n[{"title": "M1"}, {"title": "M2"}, {"title": "M3"}]'
    parsed = parse_json_response(raw)
    assert isinstance(parsed, list)
    assert [item["title"] for item in parsed] == ["M1", "M2", "M3"]


def test_a_fenced_block_after_a_fenced_sketch() -> None:
    raw = (
        "Recuerda el formato:\n```json\n{'title': str}\n```\n"
        f"Y el resultado:\n```json\n{OUTLINE_JSON}\n```"
    )
    assert parse_json_response(raw)["title"] == "Higiene alimentaria"


def test_trailing_commas_are_still_repaired() -> None:
    raw = '<think>x</think>{"lessons": [{"title": "L1"},], "exercises": [],}'
    assert parse_json_response(raw)["lessons"][0]["title"] == "L1"


# --------------------------------------------------------------------------- #
# the failure has to be diagnosable
# --------------------------------------------------------------------------- #
def test_the_error_carries_the_raw_response() -> None:
    raw = "Lo siento, no puedo generar el curso con este material."
    with pytest.raises(LLMError) as excinfo:
        parse_json_response(raw)
    message = str(excinfo.value)
    assert raw in message
    assert f"({len(raw)} chars)" in message


def test_a_long_raw_response_is_truncated_and_says_by_how_much() -> None:
    raw = "no json aqui. " * 400
    with pytest.raises(LLMError) as excinfo:
        parse_json_response(raw)
    message = str(excinfo.value)
    assert f"first {RAW_PREVIEW_CHARS} of {len(raw)} chars" in message
    assert len(message) < len(raw)
    assert raw[:200] in message


def test_the_failure_is_logged_under_a_greppable_marker(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.ERROR, logger="src.llm.parsing"):
        with pytest.raises(LLMError):
            parse_json_response("nada de json", context="design_structure")
    assert PARSE_FAILED in caplog.text
    assert "[design_structure]" in caplog.text
    assert "nada de json" in caplog.text


def test_the_context_names_the_call_site_in_the_error() -> None:
    with pytest.raises(LLMError, match=r"\[generate_modules\]"):
        parse_json_response("prosa y nada mas", context="generate_modules")


@pytest.mark.parametrize("empty", ["", "   \n ", None])
def test_an_empty_response_is_told_apart_from_an_unparseable_one(empty: str) -> None:
    with pytest.raises(LLMError, match="Empty LLM response"):
        parse_json_response(empty)


# --------------------------------------------------------------------------- #
# shape coercion: the wrapper object is optional, the content is not
# --------------------------------------------------------------------------- #
def test_a_bare_list_of_module_specs_becomes_an_outline() -> None:
    """The structure designer's shape has exactly one array field, so a bare list can
    only be ``modules``. The old code replaced it with an empty course."""
    modules = [{"title": "M1", "position": 1}, {"title": "M2", "position": 2}]
    outline = outline_dict(modules)
    assert outline["modules"] == modules
    assert "title" not in outline  # `publish` owns that default, not this helper


def test_an_outline_object_keeps_its_fields_and_normalizes_modules() -> None:
    outline = outline_dict(
        {"title": "T", "outcome": "o", "modules": [{"title": "M1"}, "basura"]}
    )
    assert outline["title"] == "T"
    assert outline["modules"] == [{"title": "M1"}]


def test_an_outline_that_cannot_be_interpreted_says_what_arrived() -> None:
    with pytest.raises(LLMError) as excinfo:
        outline_dict(["Modulo 1", "Modulo 2"])
    message = str(excinfo.value)
    assert "list of 2 item(s) of type str" in message
    assert "Modulo 1" in message


def test_a_bare_list_of_lessons_is_the_lessons_array() -> None:
    """The reported crash: ``'list' object has no attribute 'get'`` at
    ``generate_modules``. A list of lesson objects is a complete answer missing only its
    wrapper, and throwing it away would waste the most expensive call in the pipeline."""
    lessons = [
        {"title": "L1", "position": 1, "content": "# Hola"},
        {"title": "L2", "position": 2, "content": "# Adios"},
    ]
    payload = module_payload(lessons)
    assert payload["lessons"] == lessons
    assert payload["exercises"] == []


def test_a_bare_list_mixing_lessons_and_exercises_is_split_by_shape() -> None:
    """A model that drops the wrapper often flattens both arrays into one. A lesson's
    ``content`` is Markdown; an exercise's is the jsonb object from the data model."""
    lesson = {"title": "L1", "position": 1, "content": "# Hola"}
    exercise = {
        "type": "test",
        "position": 1,
        "content": {"question": "q", "options": ["a", "b"], "correct": 0},
    }
    payload = module_payload([lesson, exercise])
    assert payload["lessons"] == [lesson]
    assert payload["exercises"] == [exercise]


def test_a_single_bare_lesson_object_is_accepted() -> None:
    payload = module_payload({"title": "L1", "content": "# Hola", "position": 1})
    assert payload["lessons"][0]["title"] == "L1"


def test_the_documented_module_object_is_unchanged() -> None:
    payload = module_payload({"lessons": [{"title": "L1"}], "exercises": []})
    assert payload == {"lessons": [{"title": "L1"}], "exercises": []}


def test_a_module_object_missing_one_key_does_not_invent_the_other() -> None:
    payload = module_payload({"lessons": [{"title": "L1"}]})
    assert payload["exercises"] == []


def test_a_module_payload_with_nothing_usable_raises_with_what_arrived() -> None:
    with pytest.raises(LLMError) as excinfo:
        module_payload(["Leccion 1", "Leccion 2"])
    assert "did not return lessons or exercises" in str(excinfo.value)
    assert "Leccion 1" in str(excinfo.value)


def test_a_bare_list_of_issues_becomes_a_review_report() -> None:
    issues = [{"severity": "critical", "module_index": 0, "description": "d"}]
    report = review_report(issues)
    assert report["issues"] == issues
    assert report["passed"] is False


def test_the_review_report_never_raises() -> None:
    """The reviewer is a gate, not a producer: an unreadable report degrades to "not
    reviewed" (``tests/test_review_degrades.py``), it does not discard the course."""
    assert review_report("me niego a revisar") == {
        "passed": False,
        "overall_score": 0.0,
        "issues": [],
    }


def test_themes_list_drops_non_dict_items() -> None:
    """A bare list of theme *names* used to travel four nodes and die in ``publish``
    with ``'str' object has no attribute 'get'``."""
    assert themes_list(["higiene", "alergenos"]) == []
    assert themes_list([{"key": "higiene"}, "alergenos"]) == [{"key": "higiene"}]
    assert themes_list({"themes": [{"key": "higiene"}]}) == [{"key": "higiene"}]


# --------------------------------------------------------------------------- #
# the two fixes meet: a reasoning model that also drops the wrapper
# --------------------------------------------------------------------------- #
def test_a_thinking_model_that_drops_the_wrapper_still_yields_a_module() -> None:
    raw = (
        "<think>\nDebo responder "
        '{"lessons": [...], "exercises": [...]}. Empiezo por las lecciones.\n</think>\n'
        '[{"title": "L1", "position": 1, "content": "# Hola"}]'
    )
    payload = module_payload(parse_json_response(raw, context="generate_modules"))
    assert payload["lessons"][0]["title"] == "L1"
