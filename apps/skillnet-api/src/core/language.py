"""What a language is, for everything that has to agree on one.

Models, Pydantic schemas, routes and prompts all need the same answer to "which
languages exist and which one is the default", so it lives here, in ``core``, which
imports nothing from the rest of the application. How a language is *explained to a
model* is a different job and lives next to the prompts, in
``src/llm/prompts/language.py``.

The split matters because the two halves change for different reasons: adding a third
language is a decision about the product and touches this file, while rewording the
instruction that pins a model's output language is prompt tuning and touches the other.
"""

from __future__ import annotations

from typing import Literal

Language = Literal["es", "en"]

DEFAULT_LANGUAGE: Language = "es"

SUPPORTED_LANGUAGES: tuple[Language, ...] = ("es", "en")


def normalize_language(value: str | None) -> Language | None:
    """Turn a locale tag into a supported language, or ``None``.

    Accepts what a browser or a client actually sends: ``en``, ``EN``, ``en-US``,
    ``es_ES``. Anything else returns ``None``, which means "nobody asked for a
    language" and leaves every downstream default exactly as it was. Coercing an
    unsupported locale to Spanish instead would be worse than ignoring it: the caller
    would have no way to tell a language it chose from one it was handed.
    """
    if not value:
        return None
    tag = value.strip().replace("_", "-").split("-", 1)[0].lower()
    if tag in SUPPORTED_LANGUAGES:
        return tag  # type: ignore[return-value]
    return None


def accept_language(header: str | None) -> Language | None:
    """The best supported language in an ``Accept-Language`` header, or ``None``.

    Honors the quality values, because the header is ordered by preference only by
    convention: Chrome sends ``es-ES,es;q=0.9,en;q=0.8`` but a client is free to send
    ``en;q=0.4,es;q=0.9`` and mean Spanish. Malformed ``q`` values are treated as the
    default weight of 1.0 rather than rejected — a broken header is still a preference.
    """
    if not header:
        return None
    scored: list[tuple[float, int, Language]] = []
    for position, part in enumerate(header.split(",")):
        tag, _, params = part.strip().partition(";")
        language = normalize_language(tag)
        if language is None:
            continue
        weight = 1.0
        _, _, raw_q = params.partition("q=")
        if raw_q:
            try:
                weight = float(raw_q.strip())
            except ValueError:
                weight = 1.0
        # Position breaks ties, so an ordered header without any ``q`` still resolves
        # to the language the client wrote first.
        scored.append((-weight, position, language))
    if not scored:
        return None
    scored.sort()
    return scored[0][2]
