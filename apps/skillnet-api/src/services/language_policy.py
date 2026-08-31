"""Where the language of a generation comes from, decided in one place.

The learner never types a language. The SPA sends no locale of its own, so the only
thing that reaches the server unasked is the browser's ``Accept-Language`` — and that is
the *weakest* signal there is, because a Spanish-speaking employee reading an English
course wants the English course, not a translation of it. Hence one order, written down
once:

    explicit request  ->  ``course.language``  ->  ``organizations.settings["language"]``
                      ->  ``Accept-Language``  ->  :data:`DEFAULT_LANGUAGE`

Read it as "the closest thing to the content wins". The course is the strongest signal
because it is a property of the material the learner is looking at; the org default is
what a self-hosted deployment sets once for everybody; the header is a guess about the
person, and it only gets to decide when nothing about the *content* does.

**Why several functions instead of one.** They answer different questions and the call
sites are not interchangeable:

- :func:`resolve_language` answers "what language is this", and it *always* answers.
  Server-generated strings — a hint, a canned reply, the fallback grading feedback —
  need a real language to look up in a table, and ``None`` is not a table key.
- :func:`prompt_language` answers the narrower question a system prompt asks, and folds
  the default language back to ``None``, because ``with_language(prompt, None)`` returns
  the prompt byte for byte and that is what keeps ``src/llm/fixture_data/index.json``
  valid (``src/llm/prompts/language.py``, rule 2). Pinning the default would also be
  *wrong* on its own terms: the prompts that follow the language of the source material
  already do the right thing for a Spanish course built from a Spanish document, and
  telling them "always Spanish" would override that for an English one.
- :func:`language_for_course` is the creation path's shape of the same question, where
  there is a course row and an optional explicit request and nothing else yet.

``src/services/cache_key.py`` folds the default away for the same reason, one layer
down: a render in the default language is produced by an identical prompt, so it keeps
its existing key and nothing already cached is invalidated.

The organization's default is *not* read here. ``organizations.settings`` has one owner,
``src/services/org_features.py``, and this module asks it — a second reader with a
second name for the same key is how the two silently disagree.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.core.language import (
    DEFAULT_LANGUAGE,
    Language,
    accept_language,
    normalize_language,
)
from src.services.org_features import org_language


def ambient_language(value: str | None) -> Language | None:
    """A language nobody typed — a column default, an org setting, a browser header.

    Returns ``None`` for the default language, which is exactly where it differs from
    :func:`~src.core.language.normalize_language` and is the whole point of the
    function. ``courses.language`` is ``NOT NULL DEFAULT 'es'``, so every course that
    predates migration 0037 claims Spanish without anyone having said so. Taking that at
    face value would cost three things for a value nobody chose: every recorded fixture
    key changes (``src/llm/fixtures.py`` hashes the system prompt), a course built from
    an English document starts being translated into Spanish, and the "no request means
    no change" guarantee the directive is built on stops holding.

    An *explicit* request is honored as it comes, default or not — see
    :func:`language_for_course`. An ambient one only counts when it differs from what the
    prompts already do unprompted.
    """
    language = normalize_language(value)
    return None if language == DEFAULT_LANGUAGE else language


def course_language(course: Any) -> Language | None:
    """``course.language`` (migration 0037), or ``None`` for anything unreadable.

    Takes the object rather than the column so a caller with no course in context can
    pass ``None`` and keep one call shape. Duck-typed because the callers hold a
    ``Course``, a ``ServedRender``'s course, or nothing at all — and because the pack
    drafters are fed ``SimpleNamespace`` stand-ins in the unit tests.
    """
    if course is None:
        return None
    return normalize_language(getattr(course, "language", None))


def resolve_language(
    *,
    requested: str | None = None,
    course: Any = None,
    org_settings: Mapping[str, Any] | None = None,
    accept_language_header: str | None = None,
) -> Language:
    """The language this generation comes out in. Always answers.

    Every argument is optional and every one of them may be unrecognised: a caller with
    no course in context passes none, and an unsupported locale is ignored rather than
    coerced (see :func:`src.core.language.normalize_language`). The first step that
    recognises something wins.
    """
    return (
        normalize_language(requested)
        or course_language(course)
        or org_language(org_settings)
        or accept_language(accept_language_header)
        or DEFAULT_LANGUAGE
    )


def prompt_language(language: str | None) -> Language | None:
    """The language to hand to ``with_language``, or ``None`` to leave a prompt alone.

    ``None`` for the default language, and that is the whole point of the call: the
    existing prompts already produce it, so appending a directive that says so would buy
    nothing and cost every recorded fixture and every cached render. Only a *departure*
    from the default has to be spelled out to the model.

    Named separately from :func:`ambient_language` even though it does the same fold,
    because it reads as a different question at the call site — "what do I pass to
    ``with_language``" rather than "did anybody choose this".
    """
    return ambient_language(language)


def language_for_course(course: Any, *, explicit: str | None = None) -> Language | None:
    """The language this course's generations should come out in, or ``None``.

    ``explicit`` is what the caller asked for on this run and wins outright. The course
    row answers otherwise, and only through :func:`ambient_language`: a persisted ``'es'``
    cannot be told from the column default, so it is read as silence rather than as a
    request.

    This is the creation path's entry point. The learner path uses
    :func:`resolve_language`, which has more signals available and must always answer.
    """
    requested = normalize_language(explicit)
    if requested is not None:
        return requested
    return ambient_language(course_language(course))


__all__ = [
    "ambient_language",
    "course_language",
    "language_for_course",
    "prompt_language",
    "resolve_language",
]
