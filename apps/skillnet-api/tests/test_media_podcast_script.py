"""Unit tests for the podcast script agent's pure core (no LLM, no network).

Covers the two functions that carry the discipline: :func:`parse_script` (strict-JSON
validation, citation filtering, single-host coercion, format pinning) and the
:func:`build_prompts` / :func:`coerce_format` presets.
"""

import json

import pytest

from src.services.media.grounding import GroundedBundle, GroundedPassage
from src.services.media.subject import MediaContextError, MediaSubject
from src.services.media.podcast.script import (
    PODCAST_FORMATS,
    PodcastFormat,
    PodcastTurn,
    build_prompts,
    coerce_format,
    filter_citations,
    parse_script,
)


def _bundle(*ids: str) -> GroundedBundle:
    return GroundedBundle(
        mode="chunks",
        passages=[
            GroundedPassage(citation_id=cid, text=f"pasaje {cid}", source_title="Manual")
            for cid in ids
        ],
    )


# --------------------------------------------------------------------------------------
# coerce_format
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("deep_dive", PodcastFormat.DEEP_DIVE),
        ("deep-dive", PodcastFormat.DEEP_DIVE),
        ("Deep Dive", PodcastFormat.DEEP_DIVE),
        ("brief", PodcastFormat.THE_BRIEF),
        ("the_brief", PodcastFormat.THE_BRIEF),
        ("critique", PodcastFormat.CRITIQUE),
        ("debate", PodcastFormat.DEBATE),
        ("nonsense", PodcastFormat.DEEP_DIVE),  # unknown -> default
        (None, PodcastFormat.DEEP_DIVE),
        ("", PodcastFormat.DEEP_DIVE),
    ],
)
def test_coerce_format(value: object, expected: PodcastFormat) -> None:
    assert coerce_format(value) is expected


def test_all_formats_have_a_preset() -> None:
    for fmt in PodcastFormat:
        assert fmt in PODCAST_FORMATS
    assert PODCAST_FORMATS[PodcastFormat.THE_BRIEF].speakers == 1
    assert PODCAST_FORMATS[PodcastFormat.DEEP_DIVE].speakers == 2


# --------------------------------------------------------------------------------------
# filter_citations
# --------------------------------------------------------------------------------------
def test_filter_citations_drops_unknown_ids_and_dedupes() -> None:
    turns = [
        PodcastTurn(speaker="A", text="hola", citation_ids=["c1", "c9", "c1"]),
        PodcastTurn(speaker="B", text="adios", citation_ids=["c99"]),
    ]
    cleaned = filter_citations(turns, {"c1", "c2"})

    assert cleaned[0].citation_ids == ["c1"]  # c9 dropped, c1 de-duped
    assert cleaned[1].citation_ids == []  # c99 not in bundle


# --------------------------------------------------------------------------------------
# parse_script
# --------------------------------------------------------------------------------------
def test_parse_script_valid_two_host() -> None:
    raw = json.dumps(
        {
            "turns": [
                {"speaker": "A", "text": "Bienvenidos", "citation_ids": ["c1"]},
                {"speaker": "B", "text": "Hoy hablamos de X", "citation_ids": ["c2", "cX"]},
            ],
            "format": "deep_dive",
            "language": "es",
            "target_seconds": 200,
        }
    )
    script = parse_script(
        raw, fmt=PodcastFormat.DEEP_DIVE, valid_ids=["c1", "c2"], target_seconds=200
    )

    assert len(script.turns) == 2
    assert script.turns[0].citation_ids == ["c1"]
    assert script.turns[1].citation_ids == ["c2"]  # hallucinated cX dropped
    assert script.format is PodcastFormat.DEEP_DIVE
    assert script.target_seconds == 200


def test_parse_script_single_host_coerces_speaker_to_a() -> None:
    raw = json.dumps(
        {
            "turns": [
                {"speaker": "A", "text": "Resumen rapido", "citation_ids": []},
                {"speaker": "B", "text": "Segundo punto", "citation_ids": []},
            ],
            "format": "the_brief",
            "language": "es",
            "target_seconds": 90,
        }
    )
    script = parse_script(raw, fmt=PodcastFormat.THE_BRIEF, valid_ids=[])

    assert [t.speaker for t in script.turns] == ["A", "A"]  # B folded to A


def test_parse_script_pins_format_and_language_over_model_echo() -> None:
    # Model lied about format/language; we pin to what the caller requested.
    raw = json.dumps(
        {
            "turns": [{"speaker": "A", "text": "hola", "citation_ids": []}],
            "format": "debate",
            "language": "en",
            "target_seconds": 999,
        }
    )
    script = parse_script(
        raw, fmt=PodcastFormat.CRITIQUE, valid_ids=[], language="es", target_seconds=120
    )

    assert script.format is PodcastFormat.CRITIQUE
    assert script.language == "es"
    assert script.target_seconds == 120


def test_parse_script_tolerates_json_wrapped_in_prose() -> None:
    inner = {
        "turns": [{"speaker": "A", "text": "hola", "citation_ids": []}],
        "format": "deep_dive",
        "language": "es",
        "target_seconds": 100,
    }
    raw = f"Aqui tienes el guion:\n```json\n{json.dumps(inner)}\n```\nEspero que sirva."
    script = parse_script(raw, fmt=PodcastFormat.DEEP_DIVE, valid_ids=[])
    assert len(script.turns) == 1


def test_parse_script_rejects_no_turns() -> None:
    raw = json.dumps({"turns": [], "format": "deep_dive"})
    with pytest.raises(ValueError, match="no turns"):
        parse_script(raw, fmt=PodcastFormat.DEEP_DIVE, valid_ids=[])


def test_parse_script_rejects_non_json() -> None:
    with pytest.raises(ValueError, match="not JSON"):
        parse_script("lo siento, no puedo", fmt=PodcastFormat.DEEP_DIVE, valid_ids=[])


def test_parse_script_rejects_invalid_speaker() -> None:
    raw = json.dumps(
        {"turns": [{"speaker": "C", "text": "hola", "citation_ids": []}]}
    )
    with pytest.raises(ValueError, match="invalid turn"):
        parse_script(raw, fmt=PodcastFormat.DEEP_DIVE, valid_ids=[])


# --------------------------------------------------------------------------------------
# build_prompts
# --------------------------------------------------------------------------------------
def _subject() -> MediaSubject:
    """The identity the job runner always has — a boxing course, the bug that started this."""
    return MediaSubject(
        course_title="Boxeo para principiantes",
        node_title="La guardia",
        node_objective="Mantener las manos altas sin bajar la barbilla",
    )


def test_build_prompts_lists_valid_ids_and_injects_context() -> None:
    bundle = _bundle("c1", "c2")
    system, user = build_prompts(
        bundle,
        subject=_subject(),
        fmt=PodcastFormat.DEEP_DIVE,
        language="es",
        target_seconds=200,
    )

    assert "c1, c2" in system
    assert "JSON" in system
    assert "pasaje c1" in user  # grounded context is in the user prompt
    assert "Manual" in user


def test_build_prompts_carries_the_course_and_node_identity() -> None:
    """An episode for a boxing course must be told it is about boxing."""
    system, user = build_prompts(
        _bundle("c1"),
        subject=_subject(),
        fmt=PodcastFormat.DEEP_DIVE,
        language="es",
        target_seconds=200,
    )
    assert "Boxeo para principiantes" in system
    assert "Boxeo para principiantes" in user
    assert "La guardia" in user
    assert "Mantener las manos altas sin bajar la barbilla" in user


def test_build_prompts_without_passages_stays_on_the_subject() -> None:
    system, user = build_prompts(
        GroundedBundle(mode="empty", passages=[]),
        subject=_subject(),
        fmt=PodcastFormat.THE_BRIEF,
        language="es",
        target_seconds=90,
    )
    assert "No hay fuentes citables" in system
    assert "habla en general" not in user
    assert "Boxeo para principiantes" in user


def test_build_prompts_refuses_when_there_is_no_context_at_all() -> None:
    with pytest.raises(MediaContextError):
        build_prompts(
            GroundedBundle(mode="empty", passages=[]),
            subject=None,
            fmt=PodcastFormat.DEEP_DIVE,
            language="es",
            target_seconds=200,
        )


def test_build_prompts_includes_steering_when_present() -> None:
    _system, user = build_prompts(
        _bundle("c1"),
        subject=_subject(),
        fmt=PodcastFormat.DEBATE,
        language="es",
        target_seconds=200,
        steering="Enfocate en las devoluciones",
    )
    assert "devoluciones" in user
