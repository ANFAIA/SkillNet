"""How to tell a model what language to answer in.

Until now the product was bilingual in its interface and monolingual in what it
generates. Every prompt either wrote Spanish outright (``source.py``,
``llm_grading.py``) or told the model to follow the language of the source material
with Spanish as the fallback (``generation.py``, ``schema.py``, ``probe.py``,
``tutor.py``). That is enough when a course is built from a document and it breaks
exactly where the public demo lives: generating from a title, where there is no source
to follow. Somebody who opens the demo in English gets an English interface wrapped
around Spanish lessons.

The vocabulary itself — which languages exist, which is the default, how to read a
locale tag — lives in ``src/core/language.py``, so that models and schemas can agree on
it without importing anything from the prompt layer. This module only decides how the
rule is worded.

Two rules shape it.

1. **A requested language overrides "follow the source".** When the caller asks for
   English the material may well be Spanish, so translating is the request and not a
   deviation from it. The directive says that outright instead of leaving the model to
   weigh two instructions against each other and pick one.

2. **No request means no change at all.** ``with_language(prompt, None)`` returns the
   prompt untouched, byte for byte. That is not politeness: ``FixtureLLMService`` keys
   recorded responses on ``sha256(system + "\\x00" + user)`` (``src/llm/fixtures.py``),
   so appending a single character to a system prompt invalidates every entry in
   ``src/llm/fixture_data/index.json`` — and with them the offline tests and
   ``scripts/quality_bench.py --offline``. The default path stays identical and the
   second language is additive.

The directive also has to defend the JSON contracts. Most of these prompts demand a
strict shape with English keys and enum values (``bloom_level``, ``content_type``, the
exercise ``type``), and a model told to "write everything in Spanish" will cheerfully
translate ``"theory"`` into ``"teoria"`` and break the validator downstream. So the
directive draws the line between prose, which is translated, and the schema, which
never is.
"""

from __future__ import annotations

from src.core.language import DEFAULT_LANGUAGE, Language, normalize_language

# Written the way the prompts around them are written: Spanish, without diacritics.
_LANGUAGE_NAMES: dict[Language, str] = {"es": "espanol", "en": "ingles"}

# What the directive calls the language when it addresses the model in that language.
_ENDONYMS: dict[Language, str] = {"es": "ESPANOL", "en": "ENGLISH"}


def language_name(value: str | None) -> str:
    """The language's name in Spanish, for prompts that name it inline.

    Replaces the ``"espanol" if language.startswith("es") else language`` line that was
    copy-pasted into the four media prompt builders. That version asked the model for
    "un episodio en en" whenever the language was English — grammatically broken in the
    middle of a Spanish instruction, and the kind of thing a model answers by guessing.
    Unrecognised values fall back to the default's name rather than being passed
    through, because the caller is about to interpolate this into a sentence.
    """
    language = normalize_language(value)
    return _LANGUAGE_NAMES[language or DEFAULT_LANGUAGE]


def language_directive(language: Language) -> str:
    """The block appended to a system prompt to pin the output language.

    Stated twice on purpose: once in Spanish, because that is the language the
    surrounding prompt is written in and the rule has to read as part of it, and once in
    the target language, because naming a language in itself is the cheapest way to
    prime a model to keep writing in it.
    """
    name = _LANGUAGE_NAMES[language]
    endonym = _ENDONYMS[language]
    primer = (
        "OUTPUT LANGUAGE: write every user-visible string in English, translating the "
        "source material where needed. Never translate JSON keys or enum values."
        if language == "en"
        else "IDIOMA DE SALIDA: escribe todo el texto visible en espanol, traduciendo "
        "el material de origen cuando haga falta."
    )
    return (
        "IDIOMA DE SALIDA (esta regla manda sobre cualquier otra indicacion de idioma "
        f"de este prompt): escribe en {endonym} TODO el texto que vaya a leer una "
        "persona — titulos, resumenes, explicaciones, enunciados, opciones y "
        "retroalimentacion. Da igual en que idioma este el material de origen: si esta "
        f"en otro, traducelo al {name}; no lo copies tal cual.\n"
        "Lo que NO se traduce nunca: las claves del JSON, los nombres de campo y los "
        "valores de enumeracion (por ejemplo bloom_level, content_type o el type de "
        "cada ejercicio) van siempre en su forma original en ingles.\n"
        f"{primer}"
    )


def with_language(system_prompt: str, language: Language | None) -> str:
    """Append the output-language rule to a system prompt.

    ``None`` returns the prompt unchanged — see rule 2 in the module docstring; the
    fixture keys depend on it. Appended rather than prepended so the rule is the last
    thing the model reads before the user turn, which is where a tie between two
    conflicting instructions gets broken.
    """
    if language is None:
        return system_prompt
    return f"{system_prompt.rstrip()}\n\n{language_directive(language)}"
