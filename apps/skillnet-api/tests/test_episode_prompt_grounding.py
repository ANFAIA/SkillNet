"""The two promises a generated question has to keep, checked on the assembled prompts.

1. It asks about something the episode actually taught (grounding).
2. Its answer key points at the option its own explanation describes (coherence).

Both broke in production and neither had a test.  The failure the testers reported —
"me dice que busque por correo y la respuesta correcta es por nombre" — is promise 2
breaking, and the prompt was teaching it: every ``---ANSWER-KEY---`` example in the repo
put the right option at index 1 or 2, so a small model copied ``"correct": 1`` out of habit
regardless of where it had written the right option.  A worked example that contradicts
itself is worse than no example, and nothing here would have noticed.

These tests read the **assembled** system prompts rather than the private constants, which
is the level that matters: the constants are f-strings with doubled braces, and what the
model sees is the concatenation.  A rule that exists in a constant but never reaches the
prompt (which is exactly how the grounding anchor was lost) still fails these tests.
"""

from __future__ import annotations

import json
import re

import pytest

from src.agents.runtime.agents.interaction_designer import interaction_designer_system
from src.llm.prompts.runtime import (
    ANSWER_KEY_SENTINEL,
    EPISODE_CRITIC_SYSTEM,
    build_episode_repair_prompt,
    build_episode_revise_prompt,
    build_episode_ui_prompt,
    episode_ui_generator_system,
    ui_generator_system,
)


def _episode() -> dict:
    """A minimal public episode contract; the builder only reads an allowlist of it."""
    return {
        "dominant_action": {
            "verb": "clasificar",
            "target": "Entradas del registro diario",
            "submission_kind": "case_transition_log",
            "instructions": "Clasifica cada entrada segun el criterio de la fuente.",
        },
        "assessment_mode": "formative",
        "belief_snapshot": {"mastery": 0.4, "experience_level": "novice"},
        "budget": {"max_words": 180},
    }


# --------------------------------------------------------------------------- #
# Promise 1: the episode prompt carries the grounding anchor
# --------------------------------------------------------------------------- #
def test_episode_prompt_requires_the_assessment_to_be_answerable_from_the_screens() -> None:
    """The rule whose absence caused the reported failure.

    ``_BLOCK_CHOICE`` always carried this anchor, but ``_episode_dialect_rules`` slices
    ``_UI_GENERATOR_TAIL`` from a marker that leaves that whole block out, so the episode
    path never received it.  Asserting on the assembled prompt is the point: this passes
    only while the rule really reaches the model.
    """
    system = episode_ui_generator_system()
    normalized = " ".join(system.split()).lower()

    assert "solo se evalua lo que este episodio ha ensenado" in normalized
    # The two halves of the anchor, stated as behaviour rather than as a slogan.
    assert "no aparece en ninguna pantalla" in normalized
    assert "tampoco repitas literalmente" in normalized


def test_episode_prompt_states_the_source_is_a_ceiling_not_a_licence_to_ask() -> None:
    """"FIEL A LA FUENTE" alone is what let the model ask about untaught material.

    The source always carries more than five screens can hold, so anchoring questions to it
    authorises exactly the failure.  The narrowing has to be explicit or the two rules read
    as permission.
    """
    normalized = " ".join(episode_ui_generator_system().split()).lower()
    assert "la fuente es el techo" in normalized
    assert "el suelo de lo que puedes preguntar" in normalized


def test_episode_critic_reviews_grounding_without_claiming_to_see_the_key() -> None:
    """The critic gets the canonical program; ``validate_ui`` stripped the key from it.

    So it may judge the stem and the options and must not be asked which option is correct —
    an instruction it could only satisfy by inventing.
    """
    normalized = " ".join(EPISODE_CRITIC_SYSTEM.split()).lower()
    assert "se evalua lo ensenado?" in normalized
    assert "tiene que aparecer en alguna pantalla" in normalized
    assert "no ves la clave de respuestas" in normalized
    assert "no juzgues cual es la correcta" in normalized


# --------------------------------------------------------------------------- #
# Promise 1b: the node knows where it sits in its course
# --------------------------------------------------------------------------- #
def test_episode_prompt_places_the_node_in_its_course() -> None:
    prompt = build_episode_ui_prompt(
        episode=_episode(),
        source_context="Hechos publicos del nodo.",
        node_title="Clasificar incidencias",
        node_summary="Como decidir el tipo de una incidencia entrante.",
        siblings=["1. Registrar la incidencia — alta en el sistema", "3. Escalar"],
    )

    assert "NODO QUE SE ENSENA" in prompt
    assert "Clasificar incidencias" in prompt
    assert "Como decidir el tipo de una incidencia entrante." in prompt
    assert "OTRAS PANTALLAS DE ESTE CURSO" in prompt
    assert "1. Registrar la incidencia — alta en el sistema" in prompt
    assert "3. Escalar" in prompt
    # The siblings are scope, not material: saying so is the whole reason to send them.
    assert "Eso lo cubren otros nodos, no este." in prompt


def test_episode_prompt_is_unchanged_when_the_caller_supplies_no_node_context() -> None:
    """The three kwargs default to empty so no existing call site breaks."""
    bare = build_episode_ui_prompt(episode=_episode(), source_context="Hechos.")

    assert bare.startswith("MISION DEL EPISODIO")
    assert "NODO QUE SE ENSENA" not in bare
    assert "OTRAS PANTALLAS DE ESTE CURSO" not in bare


def test_blank_and_whitespace_siblings_do_not_open_an_empty_section() -> None:
    prompt = build_episode_ui_prompt(
        episode=_episode(), source_context="Hechos.", siblings=["", "   "]
    )
    assert "OTRAS PANTALLAS DE ESTE CURSO" not in prompt


@pytest.mark.parametrize("builder", [build_episode_repair_prompt, build_episode_revise_prompt])
def test_repair_and_revise_restate_the_whole_contract(builder) -> None:
    """A retry that drops the node context would answer a narrower question than the first
    pass was asked — and the revise pass is usually acting on "this asks something no screen
    taught", which it cannot honour while blind to which screens are its own."""
    kwargs = {
        "episode": _episode(),
        "source_context": "Hechos publicos del nodo.",
        "previous": "root = Stack([intro], \"md\")",
        "node_title": "Clasificar incidencias",
        "node_summary": "Como decidir el tipo de una incidencia entrante.",
        "siblings": ["1. Registrar la incidencia"],
    }
    kwargs["errors" if builder is build_episode_repair_prompt else "notes"] = ["algo"]

    prompt = builder(**kwargs)

    assert "Clasificar incidencias" in prompt
    assert "OTRAS PANTALLAS DE ESTE CURSO" in prompt
    assert "1. Registrar la incidencia" in prompt


# --------------------------------------------------------------------------- #
# Promise 2: every worked answer key agrees with its own question
# --------------------------------------------------------------------------- #
_QUIZ_LINE = re.compile(r"^\s*\w+\s*=\s*QuizItem\((.+)\)\s*$", re.MULTILINE)
_OPTIONS = re.compile(r"\[(.*)\]\s*$")
_STRING = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _worked_examples(prompt: str) -> list[tuple[list[str], object, str]]:
    """Every ``QuizItem`` + ``---ANSWER-KEY---`` pair written out in a prompt.

    Pairs a key block with the closest ``QuizItem`` declared above it, which is how the
    examples are laid out and how a model reads them.
    """
    examples: list[tuple[list[str], object, str]] = []
    for block in prompt.split(ANSWER_KEY_SENTINEL)[1:]:
        head, _, _ = block.partition("\n\n")
        line = next((ln for ln in head.splitlines() if ln.strip().startswith("{")), "")
        try:
            key = json.loads(line.strip())
        except (ValueError, TypeError):
            continue
        preceding = prompt.split(ANSWER_KEY_SENTINEL + block, 1)[0]
        quiz = _QUIZ_LINE.findall(preceding)
        if not quiz or not isinstance(key, dict):
            continue
        options_match = _OPTIONS.search(quiz[-1])
        options = _STRING.findall(options_match.group(1)) if options_match else []
        for entry in key.values():
            if isinstance(entry, dict) and "correct" in entry:
                examples.append((options, entry["correct"], str(entry.get("explanation", ""))))
    return examples


def _content_words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-zA-ZáéíóúñÁÉÍÓÚÑ]+", text.lower()) if len(word) >= 5}


ALL_PROMPTS = {
    "monolithic": ui_generator_system(),
    "episode": episode_ui_generator_system(),
    "interaction_designer": interaction_designer_system(),
}


@pytest.mark.parametrize("name", sorted(ALL_PROMPTS))
def test_every_worked_answer_key_indexes_a_real_option(name: str) -> None:
    """An out-of-range or mistyped index in an example teaches an ungradeable key."""
    examples = _worked_examples(ALL_PROMPTS[name])
    assert examples, f"{name}: no worked answer-key example found to check"

    for options, correct, _ in examples:
        if isinstance(correct, bool) or not options:
            continue  # true_false carries a boolean, not an index
        assert isinstance(correct, int), f"{name}: {correct!r} is not an option index"
        assert 0 <= correct < len(options), (
            f"{name}: index {correct} is outside the {len(options)} options written"
        )


@pytest.mark.parametrize("name", sorted(ALL_PROMPTS))
def test_every_worked_answer_key_explains_the_option_it_marks(name: str) -> None:
    """The check that would have caught the reported bug.

    The explanation has to describe the option at ``correct`` better than it describes any
    other — that is what "the answer matches the question" means, and an example where it
    does not is the model's template for producing the same contradiction.
    """
    for options, correct, explanation in _worked_examples(ALL_PROMPTS[name]):
        if isinstance(correct, bool) or len(options) != 4:
            continue  # two-letter placeholders carry no meaning to overlap
        explained = _content_words(explanation)
        overlap = [len(_content_words(option) & explained) for option in options]
        best = max(overlap)
        assert overlap[correct] == best and overlap.count(best) == 1, (
            f"{name}: the explanation {explanation!r} does not describe option {correct} "
            f"({options[correct]!r}); overlaps were {overlap}"
        )


def test_the_worked_examples_do_not_teach_a_favourite_position() -> None:
    """Position bias in the examples is the mechanism behind the reported failure.

    Before this, every four-option example in the repo answered 1 or 2 — never 0, never the
    last — so "write 1" was the habit the prompt itself taught.
    """
    used = {
        correct
        for prompt in ALL_PROMPTS.values()
        for options, correct, _ in _worked_examples(prompt)
        if not isinstance(correct, bool) and len(options) == 4
    }
    assert used == {0, 1, 2, 3}, f"four-option examples only ever answer {sorted(used)}"


def test_interaction_designer_examples_carry_no_concrete_domain() -> None:
    """A small model copies a worked example's TOPIC, not just its shape.

    The episode path learned this and went domain-abstract on purpose; this agent's examples
    had been left pinned to one concrete domain, so its questions arrived wearing that
    domain's vocabulary whatever the node was about.

    Scoped to the SkillNet-authored half: the generated dialect artefact above it is not
    ours to police, and its prose uses ordinary words ("entrada de datos") that a blunt
    substring check would report forever.
    """
    _artefact, marker, authored = interaction_designer_system().partition(
        "## SkillNet Interaction Designer"
    )
    assert marker, "the agent's own section moved; this test no longer checks anything"

    lowered = authored.lower()
    for leaked in ("email", "correo", "celiaco", "gluten", "alergeno", "comanda", "tpv"):
        assert leaked not in lowered, f"a concrete domain leaked into the examples: {leaked}"


def test_interaction_designer_dragorder_example_is_not_pre_solved() -> None:
    """Its items and its correct order used to be identical, so the example taught an
    exercise that comes already sorted and grades everyone correct."""
    system = interaction_designer_system()
    line = next(ln for ln in system.splitlines() if ln.strip().startswith("ejercicio = DragOrder("))
    arrays = re.findall(r"\[(.*?)\]", line)
    assert len(arrays) == 2
    assert arrays[0] != arrays[1], "the shuffled items and the correct order must differ"
