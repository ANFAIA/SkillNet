"""The v1 generation prompts tie each question to the module that teaches it.

The v2 episode path learned this the hard way (``test_episode_prompt_grounding.py``): an
assessment anchored only to the source asks about material the screen never explained,
because the source always carries more than a module can teach. The v1 prompts had the
same gap — ``MODULE_GENERATOR_SYSTEM`` only said "based on the source" and
``QUALITY_REVIEWER_SYSTEM`` only checked answers against the source — so a generated
exercise could quote any fact of the document, whatever the module covered. These tests
pin the two rules that close it.

They read the system prompts, which is the level the model sees; a rule that exists only
in a comment does not pass.
"""

from __future__ import annotations

from src.llm.prompts.generation import (
    MODULE_GENERATOR_SYSTEM,
    QUALITY_REVIEWER_SYSTEM,
)


def _normalized(prompt: str) -> str:
    return " ".join(prompt.split()).lower()


def test_the_generator_requires_the_answer_to_live_in_the_lesson() -> None:
    """The module writer has to teach a fact before it may ask about it."""
    normalized = _normalized(MODULE_GENERATOR_SYSTEM)

    assert "alineacion pregunta-leccion" in normalized
    assert "cada ejercicio se responde con lo que ensenan las lecciones de este modulo" in normalized
    # The narrowing against the source is what the old "fundamentado en el material de
    # origen" rule was missing: the source is a ceiling, not a licence to ask.
    assert "aunque si este en el material de origen" in normalized


def test_the_generator_binds_the_explanation_to_the_taught_fact() -> None:
    normalized = _normalized(MODULE_GENERATOR_SYSTEM)
    assert "la \"explanation\" de un ejercicio cerrado cita el hecho concreto" in normalized


def test_the_reviewer_checks_each_question_against_its_own_module() -> None:
    """The gate the generator's rule needs to be enforced after the fact."""
    normalized = _normalized(QUALITY_REVIEWER_SYSTEM)

    assert "alineacion pregunta-leccion" in normalized
    assert "cada ejercicio debe poder responderse con lo que ensenan las lecciones del mismo modulo" in normalized
    # The failure has to be critical, or a passing score would ship it anyway.
    assert "marcalo como \"critical\"" in normalized
    assert "pregunta que no se explico" in normalized
