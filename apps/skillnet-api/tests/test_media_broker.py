"""The media broker: preference gating, prompt addendum, and validator acceptance.

Pure unit tests (no DB): they exercise the gate/addendum/fingerprint logic and prove that a
program carrying a broker-scoped ``PodcastPlayer`` / ``InfographicImage`` validates through
the same kit gate as any other component.
"""

from __future__ import annotations

from src.agents.runtime.media_broker import (
    MediaOffer,
    gate_offers,
    offers_fingerprint,
    offers_prompt_addendum,
)
from src.render.spec import parse_spec

_PODCAST = MediaOffer(
    kind="podcast", component="PodcastPlayer", artifact_id="aaaa1111", title="Audio"
)
_INFOGRAPHIC = MediaOffer(
    kind="infographic", component="InfographicImage", artifact_id="bbbb2222", title="Info"
)
_READY = {"podcast": _PODCAST, "infographic": _INFOGRAPHIC}


def _prefs(**overrides: object) -> dict:
    base = {
        "version": 3,
        "web_presentation": "balanced",
        "modalities": [],
        "interaction": "standard",
        "detail": "standard",
        "images": "when_useful",
    }
    base.update(overrides)
    return base


def test_audio_preference_offers_only_the_podcast() -> None:
    offers = gate_offers(_READY, _prefs(modalities=["audio"]))
    assert [o.component for o in offers] == ["PodcastPlayer"]


def test_visual_preference_offers_only_the_infographic() -> None:
    offers = gate_offers(_READY, _prefs(web_presentation="visual"))
    assert [o.component for o in offers] == ["InfographicImage"]
    # `images: prefer` is an alternate visual signal.
    offers2 = gate_offers(_READY, _prefs(images="prefer"))
    assert [o.component for o in offers2] == ["InfographicImage"]


def test_balanced_preference_offers_nothing() -> None:
    assert gate_offers(_READY, _prefs()) == []
    assert gate_offers(_READY, None) == []


def test_offer_requires_a_ready_artefact() -> None:
    # Audio preference but no ready podcast -> no offer.
    assert gate_offers({"infographic": _INFOGRAPHIC}, _prefs(modalities=["audio"])) == []


def test_fingerprint_is_stable_and_empty_without_offers() -> None:
    assert offers_fingerprint([]) == ""
    fp = offers_fingerprint([_PODCAST, _INFOGRAPHIC])
    assert fp == "media:PodcastPlayer:aaaa1111,InfographicImage:bbbb2222"


def test_addendum_pins_the_real_artifact_id() -> None:
    text = offers_prompt_addendum([_PODCAST])
    assert "PodcastPlayer" in text
    assert "aaaa1111" in text
    assert offers_prompt_addendum([]) == ""


def test_a_program_with_a_podcastplayer_validates() -> None:
    payload = {
        "version": "skillnet-ui/1",
        "format": "explanation",
        "root": "root",
        "components": [
            {"id": "root", "type": "Stack", "props": {"gap": "md"}, "children": ["a", "p"]},
            {"id": "a", "type": "TextContent", "props": {"text": "Guia.", "variant": "lead"}},
            {
                "id": "p",
                "type": "PodcastPlayer",
                "props": {"artifact_id": "aaaa1111", "title": "Audio overview"},
            },
        ],
    }
    spec = parse_spec(payload)
    types = {c.type for c in spec.components}
    assert "PodcastPlayer" in types


def test_a_program_with_an_infographicimage_validates() -> None:
    payload = {
        "version": "skillnet-ui/1",
        "format": "explanation",
        "root": "root",
        "components": [
            {"id": "root", "type": "Stack", "props": {"gap": "md"}, "children": ["a", "img"]},
            {"id": "a", "type": "TextContent", "props": {"text": "Guia.", "variant": "lead"}},
            {
                "id": "img",
                "type": "InfographicImage",
                "props": {"artifact_id": "bbbb2222", "alt": "Infografia de alergenos"},
            },
        ],
    }
    spec = parse_spec(payload)
    assert "InfographicImage" in {c.type for c in spec.components}
