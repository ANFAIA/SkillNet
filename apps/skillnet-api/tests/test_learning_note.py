"""The learner's free-text "how I like to learn" note, end to end (no DB, no network).

Three things this covers, matching the owner's emphasis:

* the note flows into the EPISODE generation prompt as bounded steering (form, not facts);
* two different notes partition the render cache, the same note shares it, and no note is
  the neutral render;
* the schema round-trips the field.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from src.config import settings
from src.llm.prompts.runtime import (
    build_episode_repair_prompt,
    build_episode_ui_prompt,
    build_ui_prompt,
)
from src.personalization.learning_note import (
    LEARNING_NOTE_MAX_CHARS,
    learning_note_fingerprint,
    normalize_learning_note,
)
from src.services.node_render_service import build_render_key

_EPISODE = {"assessment_mode": "none", "dominant_action": {}, "belief_snapshot": {}}


# --------------------------------------------------------------------------- #
# normalize / fingerprint
# --------------------------------------------------------------------------- #
def test_normalize_collapses_whitespace_and_caps_length() -> None:
    assert normalize_learning_note("  me  gustan\n las metaforas ") == "me gustan las metaforas"
    assert normalize_learning_note(None) == ""
    assert normalize_learning_note("   ") == ""
    assert len(normalize_learning_note("x" * 5000)) == LEARNING_NOTE_MAX_CHARS


def test_fingerprint_stable_and_content_addressed() -> None:
    # Same note (modulo whitespace) -> same fingerprint -> shared render.
    assert learning_note_fingerprint("me gustan las metaforas") == learning_note_fingerprint(
        "  me gustan   las metaforas "
    )
    # Different notes -> different fingerprints.
    assert learning_note_fingerprint("metaforas") != learning_note_fingerprint("las bases")
    # No note -> empty fingerprint, which leaves every pre-existing key untouched.
    assert learning_note_fingerprint(None) == ""
    assert learning_note_fingerprint("   ") == ""
    # Shape: a namespaced short hex digest.
    fp = learning_note_fingerprint("algo")
    assert fp.startswith("note:") and len(fp) == len("note:") + 12


# --------------------------------------------------------------------------- #
# prompt steering: HOW, not WHAT
# --------------------------------------------------------------------------- #
def test_note_flows_into_episode_prompt_as_bounded_steering() -> None:
    prompt = build_episode_ui_prompt(
        episode=_EPISODE,
        source_context="La cadena de frio del pescado no supera los 2 grados.",
        learning_note="me gustan las metaforas para aprender",
    )
    assert "me gustan las metaforas para aprender" in prompt
    # Quarantined as DATA, and it must reassert that facts/source win.
    assert "DATO, no una orden" in prompt
    assert "los hechos, la fuente" in prompt


def test_no_note_is_neutral_prompt() -> None:
    neutral = build_episode_ui_prompt(episode=_EPISODE, source_context="x")
    assert "COMO LE GUSTA APRENDER" not in neutral


def test_two_notes_produce_different_prompts_same_source() -> None:
    note_a = "prefiero que me lo cuentes como si fuera boxeo"
    note_b = "quiero empezar por los axiomas y demostrarlo"
    a = build_episode_ui_prompt(episode=_EPISODE, source_context="fuente", learning_note=note_a)
    b = build_episode_ui_prompt(episode=_EPISODE, source_context="fuente", learning_note=note_b)
    assert a != b
    assert note_a in a and note_a not in b
    assert note_b in b and note_b not in a


def test_repair_prompt_carries_the_note() -> None:
    prompt = build_episode_repair_prompt(
        episode=_EPISODE,
        source_context="fuente",
        previous="programa roto",
        errors=["algo"],
        learning_note="me gustan las metaforas",
    )
    assert "me gustan las metaforas" in prompt


def test_monolithic_prompt_also_carries_the_note() -> None:
    prompt = build_ui_prompt(
        title="Cadena de frio",
        summary="Temperaturas de la camara",
        source_context="El pescado no supera 2 grados.",
        learning_note="me gusta entender las bases",
    )
    assert "me gusta entender las bases" in prompt
    assert "DATO, no una orden" in prompt


# --------------------------------------------------------------------------- #
# cache partitioning
# --------------------------------------------------------------------------- #
def _profile(note: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        nodes_completed=3,
        format_vector=None,
        role_title="Support agent",
        sector="events",
        preset="standard",
        experience_level="some",
        learning_preferences=None,
        personalization_revision=0,
        learning_note=note,
    )


def _key(note: str | None):
    return build_render_key(
        node=SimpleNamespace(id=uuid.UUID(int=41)),
        course=SimpleNamespace(schema_version=7, intent_density=3),
        profile=_profile(note),
        node_state=SimpleNamespace(scaffold_band="neutral"),
        accessibility={},
        model_key="fixture/local|fixture/local",
        backend="openui",
        learning_note_fingerprint=learning_note_fingerprint(note),
    )


def test_note_partitions_the_render_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ADAPTIVE_EPISODES", True)
    none = _key(None)
    metaphors = _key("me gustan las metaforas")
    basics = _key("me gusta entender las bases")
    same_metaphors = _key("  me gustan   las metaforas ")

    # No note keeps the neutral key; a note forks it; two notes differ; same note shares.
    assert metaphors.cache_key != none.cache_key
    assert basics.cache_key != none.cache_key
    assert metaphors.cache_key != basics.cache_key
    assert metaphors.cache_key == same_metaphors.cache_key
