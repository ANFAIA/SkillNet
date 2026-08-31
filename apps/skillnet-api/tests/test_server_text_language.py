"""Spanish that no prompt can fix: hints, canned replies, feedback, progress lines.

Four surfaces the learner reads that are **not** generations. They were Spanish literals in
the source, so the bilingual interface wrapped them unchanged and an English reviewer got
Spanish hints under an English lesson. Each one is now a small table in the module that
owns the text, and these tests hold three things:

* the default language is unchanged, word for word — this is user-visible copy, and
  "improving it while I was in there" is how a translation pass becomes a content change;
* the second language exists for **every** key, because a half-filled table is a
  ``KeyError`` in front of a learner;
* one owner per sentence. The Didact ladder and the ``QuizItem`` ladder used to carry
  separate copies of the same six sentences and had already drifted apart in wording and
  accents; the fence against that happening again is here.
"""

from __future__ import annotations

import pytest

from src.agents.runtime.nodes import _STEP_MESSAGES, STEP_MESSAGES, step_message
from src.core.language import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES
from src.routes.nodes import _hint_for
from src.services.activity_hints import _PHRASES, activity_hint
from src.services.llm_grading import _PENDING_FEEDBACK, _pending
from src.services.small_talk import (
    _REPLIES,
    _TUTOR_REPLIES,
    classify_small_talk,
    small_talk_reply,
)

_KINDS = ("greeting", "thanks", "farewell", "identity")


# ------------------------------------------------------------------ completeness


@pytest.mark.parametrize(
    ("name", "table"),
    [
        ("activity hint phrases", _PHRASES),
        ("graph step messages", _STEP_MESSAGES),
        ("admin canned replies", _REPLIES),
        ("tutor canned replies", _TUTOR_REPLIES),
    ],
)
def test_every_table_covers_every_supported_language_with_the_same_keys(name, table):
    assert set(table) == set(SUPPORTED_LANGUAGES), name
    reference = set(table[DEFAULT_LANGUAGE])
    for language, entries in table.items():
        # A key present in one language and missing in another is a ``KeyError`` raised at
        # the worst possible moment: while somebody is stuck on a question.
        assert set(entries) == reference, f"{name} / {language}"
        assert all(value.strip() for value in entries.values()), f"{name} / {language}"


def test_the_pending_grading_feedback_exists_in_both_languages():
    assert set(_PENDING_FEEDBACK) == set(SUPPORTED_LANGUAGES)
    assert _pending(None).feedback == _PENDING_FEEDBACK[DEFAULT_LANGUAGE]
    assert _pending("en").feedback == "Answer recorded. Pending review."
    # Not a judgement about the answer, just the absence of one — unchanged.
    assert _pending("en").score == 0.5
    assert _pending("en").passed is False


# ------------------------------------------------------------------ the hints


def _quiz_props() -> dict:
    return {
        "item_id": "q1",
        "item_type": "test",
        "options": ["A los 14 dias", "A los 30 dias", "A los 7 dias", "Nunca caduca"],
    }


class _Node:
    summary = "El plazo de devolucion es de 30 dias."


def test_the_quiz_ladder_is_unchanged_in_the_default_language():
    """The wording a learner sees today, pinned. Rung 2 and 3 are the risky ones.

    ``_hint_for`` used to hold its own accent-free copies of these sentences; they now come
    from ``activity_hints``, which had the accented ones. That *is* a visible change to
    rungs 2 and 3's fallbacks and it is the point — one owner — so the two that were
    identical in both copies are asserted verbatim here.
    """
    key = {"correct": 1, "explanation": "Lo dice la ficha del producto."}
    assert _hint_for(1, node=_Node(), item_props=_quiz_props(), key_entry=key) == (
        "Vuelve a la idea del nodo: El plazo de devolucion es de 30 dias."
    )
    assert _hint_for(2, node=_Node(), item_props=_quiz_props(), key_entry=key) == (
        'Puedes descartar "A los 14 dias" y "A los 7 dias".'
    )
    assert _hint_for(3, node=_Node(), item_props=_quiz_props(), key_entry=key) == (
        "Lo dice la ficha del producto."
    )


def test_the_quiz_ladder_speaks_english_when_the_course_does():
    key = {"correct": 1}
    first = _hint_for(
        1, node=_Node(), item_props=_quiz_props(), key_entry=key, language="en"
    )
    second = _hint_for(
        2, node=_Node(), item_props=_quiz_props(), key_entry=key, language="en"
    )
    third = _hint_for(
        3, node=_Node(), item_props=_quiz_props(), key_entry=key, language="en"
    )
    assert first.startswith("Back to the idea of the lesson:")
    assert second == 'You can rule out "A los 14 dias" and "A los 7 dias".'
    assert third.startswith("It is the answer that follows directly")


def test_an_authored_explanation_is_never_translated():
    """Rung 3 hands over what the author wrote, in the language the author wrote it in.

    Restating it would be inventing content: the explanation is the course's own words and
    the only thing on this ladder that is not platform copy.
    """
    authored = "Lo dice la ficha del producto."
    assert (
        _hint_for(
            3,
            node=_Node(),
            item_props=_quiz_props(),
            key_entry={"correct": 1, "explanation": authored},
            language="en",
        )
        == authored
    )
    assert (
        activity_hint(
            3,
            component_id="DidactMultipleChoice",
            public_definition={},
            evaluation={"mode": "exact", "explanation": authored},
            node_summary=None,
            language="en",
        )
        == authored
    )


def test_both_ladders_say_the_same_sentence_for_the_same_rung():
    """The duplicate this batch removed. Two ladders, one vocabulary.

    Rung 1 and the two fallbacks are platform copy and identical by construction now.
    Anything item-shaped (which options to rule out, which step is first) still differs,
    because the items differ — that is traversal, not wording.
    """
    for language in SUPPORTED_LANGUAGES:
        quiz = _hint_for(
            1,
            node=_Node(),
            item_props=_quiz_props(),
            key_entry=None,
            language=language,
        )
        didact = activity_hint(
            1,
            component_id="DidactMultipleChoice",
            public_definition={},
            evaluation={},
            node_summary=_Node.summary,
            language=language,
        )
        assert quiz == didact, language

        quiz_fallback = _hint_for(
            2,
            node=_Node(),
            item_props={"item_id": "q1", "item_type": "test", "options": []},
            key_entry={},
            language=language,
        )
        didact_fallback = activity_hint(
            2,
            component_id="DidactUnknownThing",
            public_definition={},
            evaluation={"mode": "something_new"},
            node_summary=None,
            language=language,
        )
        assert quiz_fallback == didact_fallback, language


def test_an_unrecognised_language_gets_the_default_rather_than_an_exception():
    """A hint that raises is worse than a hint in the wrong language."""
    assert _hint_for(
        1, node=_Node(), item_props=_quiz_props(), key_entry=None, language="klingon"
    ) == _hint_for(1, node=_Node(), item_props=_quiz_props(), key_entry=None)


# ------------------------------------------------------------------ small talk


def test_the_matcher_is_shared_and_only_the_reply_has_a_language():
    """"hello" is a greeting in either table; what it is answered *with* is the choice.

    Answering in whatever language the greeting happened to be typed in would switch the
    surface mid-conversation — "hi" is a perfectly ordinary thing to type in Spanish.
    """
    for phrase in ("hola", "hello", "good morning", "que tal"):
        assert classify_small_talk(phrase) == "greeting", phrase
    assert small_talk_reply("hello", language="es").startswith("Hola.")
    assert small_talk_reply("hola", language="en").startswith("Hi.")


def test_a_real_question_still_reaches_the_real_path_in_both_languages():
    assert classify_small_talk("how are my people doing?") is None
    assert classify_small_talk("hola, como van mis empleados") is None
    assert small_talk_reply("what does the allergen manual say?", language="en") is None


def test_each_audience_keeps_its_own_promises_in_english():
    """The admin lists admin capabilities and the tutor lists learning help — in both."""
    admin = small_talk_reply("who are you", audience="admin", language="en") or ""
    tutor = small_talk_reply("who are you", audience="tutor", language="en") or ""
    assert "your team" in admin
    assert "courses" in tutor
    # A capability promised here is a refusal three messages later, so the tutor must not
    # offer what only the admin data path can deliver.
    assert "deadline" not in tutor


# ------------------------------------------------------------------ step messages


def test_the_progress_lines_are_unchanged_by_default_and_translated_on_request():
    assert STEP_MESSAGES is _STEP_MESSAGES[DEFAULT_LANGUAGE]
    assert step_message("genera_ui") == "Escribiendo la leccion..."
    assert step_message("genera_ui", "es") == "Escribiendo la leccion..."
    assert step_message("genera_ui", "en") == "Writing the lesson..."
    # An unknown step is its own key rather than a KeyError: the graph publishes progress
    # on a path where an exception would abort a render that was going fine.
    assert step_message("a_step_nobody_added_yet", "en") == "a_step_nobody_added_yet"
