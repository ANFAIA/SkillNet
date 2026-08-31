"""The language of a generation: where it comes from, and what it must not disturb.

Two halves, and the second one is the reason this file exists.

The first half is ordinary: :func:`resolve_language` implements the order documented in
``src/services/language_policy.py`` and these tests pin each step of it.

The second half is a **regression fence**. Adding a second language to a system that
records LLM responses by ``sha256(system + "\\x00" + user)`` is one careless keystroke away
from invalidating ``src/llm/fixture_data/index.json``, and with it every offline test and
``scripts/quality_bench.py --offline``. The same keystroke would evict every cached render
in every deployment. So the invariant is asserted directly and separately for every prompt
builder that grew a ``language`` argument: **the default path is byte-identical**. If one of
these fails, the fix is never to re-record a fixture.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from src.core.language import DEFAULT_LANGUAGE
from src.llm.prompts.admin import admin_genui_system_prompt, admin_system_prompt
from src.llm.prompts.explain import EXPLAIN_SYSTEM, build_explain_messages
from src.llm.prompts.runtime import (
    EPISODE_CRITIC_SYSTEM,
    episode_critic_system,
    episode_ui_generator_system,
    episode_ui_repair_system,
    episode_ui_revise_system,
    ui_generator_system,
    ui_repair_system,
)
from src.llm.prompts.tutor import tutor_genui_system_prompt, tutor_system_prompt
from src.services.org_features import ORG_LANGUAGE
from src.services.language_policy import (
    prompt_language,
    resolve_language,
)

# ------------------------------------------------------------------- the order


def _course(language: str) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), language=language)


def test_the_resolution_order_is_request_then_course_then_org_then_header():
    course = _course("en")
    org = {ORG_LANGUAGE: "es"}

    # 1. An explicit request wins over everything, including the course it is about:
    #    that is what makes "explain this in English" answerable inside a Spanish course.
    assert (
        resolve_language(
            requested="es",
            course=_course("en"),
            org_settings=org,
            accept_language_header="en",
        )
        == "es"
    )
    # 2. The course beats the org default and the browser, because it is a property of
    #    the material on screen rather than a guess about the reader.
    assert (
        resolve_language(course=course, org_settings=org, accept_language_header="es")
        == "en"
    )
    # 3. The org default beats the browser.
    assert (
        resolve_language(
            org_settings={ORG_LANGUAGE: "en"}, accept_language_header="es"
        )
        == "en"
    )
    # 4. The browser decides only when nothing about the content does.
    assert resolve_language(accept_language_header="en-GB,en;q=0.9") == "en"
    # 5. And with nothing at all, the platform default.
    assert resolve_language() == DEFAULT_LANGUAGE


def test_an_unreadable_step_is_skipped_rather_than_coerced():
    """Each step is allowed to be absent, malformed or unsupported without deciding."""
    assert resolve_language(requested="fr", course=_course("en")) == "en"
    assert resolve_language(course=SimpleNamespace()) == DEFAULT_LANGUAGE
    assert resolve_language(course=None, org_settings={}) == DEFAULT_LANGUAGE
    assert resolve_language(org_settings={ORG_LANGUAGE: "klingon"}) == (
        DEFAULT_LANGUAGE
    )


def test_prompt_language_folds_the_default_away():
    """The fold that protects every fixture and every cached render.

    A render in the default language is produced by a byte-identical prompt, so it must
    not be told which language it is in: saying so would append a directive, change the
    hash, and evict everything already recorded and cached — for a language the prompts
    were already writing in.
    """
    assert prompt_language(None) is None
    assert prompt_language(DEFAULT_LANGUAGE) is None
    assert prompt_language("es_ES") is None
    assert prompt_language("en") == "en"
    assert prompt_language("en-US") == "en"
    # Unsupported is "nobody asked", so it leaves the prompt alone too.
    assert prompt_language("fr") is None


# --------------------------------------------------- the prompts, additively

_COMPONENTS = "## Component Signatures\n\nStack(children, gap)\n"


def _pairs() -> list[tuple[str, object]]:
    """Every system prompt on the learner's path that grew a ``language`` argument."""
    return [
        ("ui_generator_system", lambda **kw: ui_generator_system(_COMPONENTS, **kw)),
        ("ui_repair_system", lambda **kw: ui_repair_system(_COMPONENTS, **kw)),
        (
            "ui_generator_system+didact",
            lambda **kw: ui_generator_system(
                _COMPONENTS, didact_verification=True, **kw
            ),
        ),
        (
            "episode_ui_generator_system",
            lambda **kw: episode_ui_generator_system(_COMPONENTS, **kw),
        ),
        (
            "episode_ui_repair_system",
            lambda **kw: episode_ui_repair_system(_COMPONENTS, **kw),
        ),
        (
            "episode_ui_revise_system",
            lambda **kw: episode_ui_revise_system(_COMPONENTS, **kw),
        ),
        ("episode_critic_system", lambda **kw: episode_critic_system(**kw)),
        ("tutor_system_prompt", lambda **kw: tutor_system_prompt("chunks", **kw)),
        (
            "tutor_genui_system_prompt",
            lambda **kw: tutor_genui_system_prompt("general", **kw),
        ),
        ("admin_system_prompt", lambda **kw: admin_system_prompt("document", **kw)),
        (
            "admin_genui_system_prompt",
            lambda **kw: admin_genui_system_prompt("general", org_data=True, **kw),
        ),
    ]


def test_no_prompt_moves_a_single_byte_without_an_explicit_language():
    for name, build in _pairs():
        assert build() == build(language=None), name


def test_every_prompt_pins_the_language_when_one_is_asked_for():
    for name, build in _pairs():
        english = build(language="en")
        default = build()
        assert english != default, name
        # The rule is appended, so nothing that was there before has moved.
        assert english.startswith(default.rstrip()), name
        assert "IDIOMA DE SALIDA" in english, name
        assert "ENGLISH" in english, name
        # And it must not contradict the JSON contracts these prompts depend on.
        assert "Lo que NO se traduce nunca" in english, name
        assert "valores de enumeracion" in english, name


def test_the_critic_keeps_its_own_rules_when_the_language_is_pinned():
    english = episode_critic_system("en")
    assert EPISODE_CRITIC_SYSTEM.rstrip() in english
    # Its own "do not change the language" instruction survives: the directive pins what
    # the critic writes, and the reviser is handed the rule separately.
    assert "ni el idioma" in english


def test_explain_pins_the_language_on_the_system_turn_only():
    """The bug: ``ExplainRequest.language`` keyed the cache and never left the server."""
    spanish = build_explain_messages("plazo", "El plazo es de 30 dias.")
    english = build_explain_messages("plazo", "El plazo es de 30 dias.", language="en")

    assert spanish[0]["content"] == EXPLAIN_SYSTEM
    assert "ENGLISH" in english[0]["content"]
    # The user turn is fenced study material and scaffolding; it says nothing about
    # language, so pinning it there would only be a second place to keep in sync.
    assert english[1]["content"] == spanish[1]["content"]
