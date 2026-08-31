"""The language vocabulary, and the two places it must not leak into.

Three things are being protected here, in order of how expensive they are to get wrong:

1. **The default path is byte-identical.** ``with_language(p, None)`` returns ``p``, and a
   cache key built without a language matches the one built with the default. Both hold
   the same line: the recorded LLM fixtures are indexed by ``sha256`` of the prompt
   (``src/llm/fixtures.py``) and every cached render by the key material, so a stray
   suffix in either place silently invalidates work that already exists.
2. **A non-default language does separate.** The mirror image of (1), and the reason the
   English demo does not serve the Spanish screen already cached for the same node.
3. **Locale parsing survives real clients.** ``en-US``, ``es_ES``, weights out of order,
   a malformed ``q``. All observed shapes, none of them worth a 500.

No DB, no network.
"""

import uuid

import pytest

from src.core.language import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    accept_language,
    normalize_language,
)
from src.llm.prompts.language import language_directive, language_name, with_language
from src.services.cache_key import build_cache_key, cache_key_material

BASE = dict(
    node_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
    schema_version=3,
    preset="standard",
    experience_level="some",
    scaffold_band="neutral",
    effective_density=3,
    backend="openui",
    model="gpt-4o-mini",
    prompt_version="runtime/44",
)


# --- 1. the default path does not move ------------------------------------------------


def test_no_language_leaves_the_prompt_untouched() -> None:
    prompt = "Eres un analista de contenido pedagogico."
    assert with_language(prompt, None) is prompt


def test_default_language_does_not_change_the_cache_key() -> None:
    """The whole point of making the language part conditional.

    If this fails, every render cached before the column existed has just been orphaned.
    """
    assert build_cache_key(**BASE) == build_cache_key(**BASE, language=DEFAULT_LANGUAGE)
    assert build_cache_key(**BASE) == build_cache_key(**BASE, language="es-ES")
    assert "lang:" not in cache_key_material(**BASE, language=DEFAULT_LANGUAGE)


def test_unsupported_language_does_not_change_the_cache_key() -> None:
    """An unknown locale is not a language, so it must not fork the keyspace.

    Otherwise a client sending ``fr`` gets its own set of cached Spanish renders.
    """
    assert build_cache_key(**BASE) == build_cache_key(**BASE, language="fr")
    assert build_cache_key(**BASE) == build_cache_key(**BASE, language="")


# --- 2. a non-default language does separate ------------------------------------------


def test_non_default_language_forks_the_cache_key() -> None:
    assert build_cache_key(**BASE) != build_cache_key(**BASE, language="en")
    assert "lang:en" in cache_key_material(**BASE, language="en")
    # And the tag is normalised before it reaches the key, so two spellings of the same
    # language share the cache instead of paying twice for it.
    assert build_cache_key(**BASE, language="en") == build_cache_key(
        **BASE, language="en-GB"
    )


def test_requested_language_reaches_the_prompt() -> None:
    prompt = "Eres un analista de contenido pedagogico."
    english = with_language(prompt, "en")
    assert english.startswith(prompt)
    assert "ENGLISH" in english
    # The rule has to claim precedence, because the prompts it is appended to already
    # carry a contradictory one ("escribe en el idioma del material de origen").
    assert "manda sobre cualquier otra indicacion de idioma" in english
    # And it has to protect the JSON contract, or the model translates the enum values
    # and the validator downstream rejects its own schema.
    assert "claves del JSON" in english


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_every_supported_language_has_a_directive(language: str) -> None:
    directive = language_directive(language)  # type: ignore[arg-type]
    assert directive.strip()
    assert language_name(language) in directive


# --- 3. locale parsing ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("en", "en"),
        ("EN", "en"),
        ("en-US", "en"),
        ("es_ES", "es"),
        ("  es  ", "es"),
        ("fr", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_language(raw: str | None, expected: str | None) -> None:
    assert normalize_language(raw) == expected


def test_language_name_never_interpolates_a_bare_tag() -> None:
    """The bug this replaced asked a model for "un episodio en en"."""
    assert language_name("en") == "ingles"
    assert language_name("en-US") == "ingles"
    assert language_name("es") == "espanol"
    assert language_name("fr") == language_name(DEFAULT_LANGUAGE)
    assert language_name(None) == language_name(DEFAULT_LANGUAGE)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("es-ES,es;q=0.9,en;q=0.8", "es"),
        ("en-US,en;q=0.9,es;q=0.8", "en"),
        # Order is a convention, ``q`` is the contract: this header means Spanish.
        ("en;q=0.4,es;q=0.9", "es"),
        # Unsupported languages are skipped rather than making the header unreadable.
        ("fr-FR,fr;q=0.9,en;q=0.5", "en"),
        # A malformed weight is still a preference.
        ("en;q=abc,es;q=0.5", "en"),
        ("fr", None),
        ("", None),
        (None, None),
    ],
)
def test_accept_language(header: str | None, expected: str | None) -> None:
    assert accept_language(header) == expected
