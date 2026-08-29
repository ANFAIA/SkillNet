"""The media broker: preference gating, prompt addendum, and validator acceptance.

Pure unit tests (no DB): they exercise the gate/addendum/fingerprint logic and prove that a
program carrying a broker-scoped ``PodcastPlayer`` / ``InfographicImage`` validates through
the same kit gate as any other component.

The last section covers the one async part, :func:`ready_media_for_node`, with a faked
session: a ``done`` artefact whose file the deployment lost must not be offered to the
generator at all.
"""

from __future__ import annotations

import logging
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agents.runtime.media_broker import (
    MEDIA_COMPONENT_BY_KIND,
    MediaOffer,
    gate_offers,
    offers_fingerprint,
    offers_prompt_addendum,
    ready_media_for_node,
)
from src.models import MediaKind
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


# --------------------------------------------------------------------------------------
# The lookup: `done` is not enough, the file has to be there
# --------------------------------------------------------------------------------------
# The bug: the lookup filtered on ``status == done`` alone, so a podcast whose mp3 had
# gone with the media volume was still offered to the generator — which placed a
# `PodcastPlayer` the learner cannot play, in a lesson then cached under a key naming it.
# One `stat` per offered row (at most two per node) keeps the loss in the log, not the
# lesson.

_NODE_ID = uuid.uuid4()
_ORG_ID = uuid.uuid4()


def _row(kind: str, asset_path: object, *, title: str = "Audio") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        kind=kind,
        asset_path=asset_path,
        spec_json={"title": title},
    )


def _session(rows: list[SimpleNamespace]) -> SimpleNamespace:
    """A session that answers the one query, and explodes if the broker tries to write."""
    scalars = SimpleNamespace(all=lambda: rows)

    async def _refuse() -> None:
        raise AssertionError("the broker must not write inside a render's transaction")

    return SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda: scalars)),
        commit=_refuse,
        rollback=_refuse,
    )


async def _offers(rows: list[SimpleNamespace]) -> dict:
    return await ready_media_for_node(
        _session(rows), node_id=_NODE_ID, org_id=_ORG_ID
    )


async def test_a_done_artefact_with_its_file_is_offered(tmp_path) -> None:
    path = tmp_path / "podcast.mp3"
    path.write_bytes(b"id3")

    offers = await _offers([_row(MediaKind.PODCAST.value, str(path))])

    assert list(offers) == [MediaKind.PODCAST.value]
    assert offers[MediaKind.PODCAST.value].component == "PodcastPlayer"


async def test_a_done_artefact_whose_file_is_gone_is_not_offered(tmp_path) -> None:
    offers = await _offers([_row(MediaKind.PODCAST.value, str(tmp_path / "gone.mp3"))])

    assert offers == {}


async def test_the_withheld_offer_says_why_in_the_log(
    tmp_path, caplog: pytest.LogCaptureFixture
) -> None:
    """Otherwise a lesson silently loses its podcast and nothing records the reason."""
    row = _row(MediaKind.PODCAST.value, str(tmp_path / "gone.mp3"))

    with caplog.at_level(logging.WARNING):
        assert await _offers([row]) == {}

    records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert records, "withholding an offer must leave a trace"
    message = records[0].getMessage()
    assert "gone.mp3" in message
    assert str(row.id) in message


async def test_an_older_artefact_with_its_file_takes_over(tmp_path) -> None:
    """Newest wins, but not when the newest is the one that lost its bytes."""
    older = tmp_path / "older.mp3"
    older.write_bytes(b"id3")
    rows = [
        _row(MediaKind.PODCAST.value, str(tmp_path / "newest.mp3"), title="Nuevo"),
        _row(MediaKind.PODCAST.value, str(older), title="Viejo"),
    ]

    offers = await _offers(rows)

    assert offers[MediaKind.PODCAST.value].artifact_id == str(rows[1].id)
    assert offers[MediaKind.PODCAST.value].title == "Viejo"


async def test_a_spec_only_row_is_still_skipped_without_a_syscall(tmp_path) -> None:
    """No ``asset_path`` never promised bytes; the check must not turn that into a stat."""
    assert await _offers([_row(MediaKind.PODCAST.value, None)]) == {}
    assert await _offers([_row(MediaKind.PODCAST.value, "")]) == {}


async def test_the_lookup_stops_once_both_kinds_are_resolved(
    tmp_path, caplog: pytest.LogCaptureFixture
) -> None:
    """A node regenerated fifty times must not cost fifty syscalls."""
    podcast = tmp_path / "p.mp3"
    podcast.write_bytes(b"id3")
    infographic = tmp_path / "i.png"
    infographic.write_bytes(b"\x89PNG")
    rows = [
        _row(MediaKind.PODCAST.value, str(podcast)),
        _row(MediaKind.INFOGRAPHIC.value, str(infographic)),
        # Older, lost, and never reached: the loop is done before it gets here.
        _row(MediaKind.PODCAST.value, str(tmp_path / "old.mp3")),
    ]

    with caplog.at_level(logging.WARNING):
        offers = await _offers(rows)

    assert len(offers) == len(MEDIA_COMPONENT_BY_KIND)
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []
