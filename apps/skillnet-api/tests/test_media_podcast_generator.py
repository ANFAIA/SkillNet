"""Unit tests for the podcast generator + voice-path selection (no LLM/ElevenLabs/network).

The LLM script call and the ElevenLabs/TTS calls are monkeypatched; what is exercised is
the generator's own logic — spec_json shape, citation persistence, progress emission — and
the voice layer's cache/dialogue/fallback selection.
"""

from pathlib import Path

import pytest

from src.models import MediaKind
from src.services.media.grounding import GroundedBundle, GroundedPassage
from src.services.media.jobs import MediaJobContext
from src.services.media.podcast import voices as voices_mod
from src.services.media.podcast.generator import PodcastGenerator
from src.services.media.podcast.script import PodcastFormat, PodcastScript, PodcastTurn


def _bundle() -> GroundedBundle:
    return GroundedBundle(
        mode="chunks_fts",
        passages=[
            GroundedPassage(citation_id="c1", text="t1", source_title="Manual", page=3),
            GroundedPassage(citation_id="c2", text="t2", source_title="Manual"),
        ],
    )


def _script() -> PodcastScript:
    return PodcastScript(
        turns=[
            PodcastTurn(speaker="A", text="Hola", citation_ids=["c1"]),
            PodcastTurn(speaker="B", text="Que tal", citation_ids=["c2"]),
        ],
        format=PodcastFormat.DEEP_DIVE,
        language="es",
        target_seconds=200,
    )


# --------------------------------------------------------------------------------------
# PodcastGenerator.generate — state and spec_json shape
# --------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generate_persists_turns_citations_and_emits_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_generate_script(bundle, **kwargs):
        assert kwargs["fmt"] is PodcastFormat.DEEP_DIVE
        return _script()

    async def fake_synthesize(script, **kwargs):
        return voices_mod.SynthesisResult(data=b"MP3BYTES", ext="mp3", voice_path="dialogue")

    monkeypatch.setattr(
        "src.services.media.podcast.generator.script_mod.generate_script",
        fake_generate_script,
    )
    monkeypatch.setattr(
        "src.services.media.podcast.generator.voices_mod.synthesize_podcast",
        fake_synthesize,
    )

    steps: list[tuple[str, dict]] = []

    async def report(step: str, extra: dict) -> None:
        steps.append((step, extra))

    ctx = MediaJobContext(
        kind=MediaKind.PODCAST,
        spec={"format": "deep-dive", "language": "es"},
        bundle=_bundle(),
        progress=report,
    )

    produced = await PodcastGenerator().generate(ctx)

    assert produced.data == b"MP3BYTES"
    assert produced.ext == "mp3"
    spec = produced.spec_json
    assert spec["generator"] == "podcast"
    assert spec["format"] == "deep_dive"
    assert spec["voice_path"] == "dialogue"
    assert spec["grounding_mode"] == "chunks_fts"
    # Transcript with per-turn citation ids is persisted for the parallel panel.
    assert [t["citation_ids"] for t in spec["turns"]] == [["c1"], ["c2"]]
    # Citation metadata resolves each id to a document/section/page.
    assert {c["citation_id"] for c in spec["citations"]} == {"c1", "c2"}
    # The three progress steps fired in order.
    assert [s[0] for s in steps] == ["guion", "voz", "listo"]
    assert steps[-1][1]["voice_path"] == "dialogue"


@pytest.mark.asyncio
async def test_generate_without_progress_reporter_is_silent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_generate_script(bundle, **kwargs):
        return _script()

    async def fake_synthesize(script, **kwargs):
        return voices_mod.SynthesisResult(data=b"X", ext="mp3", voice_path="fallback")

    monkeypatch.setattr(
        "src.services.media.podcast.generator.script_mod.generate_script",
        fake_generate_script,
    )
    monkeypatch.setattr(
        "src.services.media.podcast.generator.voices_mod.synthesize_podcast",
        fake_synthesize,
    )

    # No progress reporter: emit() must be a no-op, not a crash.
    ctx = MediaJobContext(kind=MediaKind.PODCAST, spec={}, bundle=_bundle())
    produced = await PodcastGenerator().generate(ctx)
    assert produced.spec_json["voice_path"] == "fallback"


# --------------------------------------------------------------------------------------
# synthesize_podcast — cache / dialogue / fallback selection
# --------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_synthesize_uses_cache_when_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cache = voices_mod.PodcastAudioCache(tmp_path)
    script = _script()
    cache.put(voices_mod.script_hash(script), b"CACHED")

    # Any attempt to actually synthesize would be a bug: fail loudly if reached.
    async def boom(*a, **k):
        raise AssertionError("should not synthesize on a cache hit")

    monkeypatch.setattr(voices_mod, "synthesize_dialogue", boom)
    monkeypatch.setattr(voices_mod, "synthesize_fallback", boom)

    result = await voices_mod.synthesize_podcast(script, cache=cache)
    assert result.voice_path == "cache"
    assert result.data == b"CACHED"


@pytest.mark.asyncio
async def test_synthesize_falls_back_when_dialogue_unsupported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cache = voices_mod.PodcastAudioCache(tmp_path)

    async def unsupported(script):
        raise voices_mod.DialogueUnsupported("no SDK")

    async def fake_fallback(script, **kwargs):
        return b"FALLBACKMP3"

    monkeypatch.setattr(voices_mod, "synthesize_dialogue", unsupported)
    monkeypatch.setattr(voices_mod, "synthesize_fallback", fake_fallback)

    result = await voices_mod.synthesize_podcast(_script(), cache=cache)
    assert result.voice_path == "fallback"
    assert result.data == b"FALLBACKMP3"
    # And it was cached for next time.
    assert cache.get(voices_mod.script_hash(_script())) == b"FALLBACKMP3"


@pytest.mark.asyncio
async def test_synthesize_prefers_dialogue_when_available(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cache = voices_mod.PodcastAudioCache(tmp_path)

    async def fake_dialogue(script):
        return b"DIALOGUEMP3"

    async def boom_fallback(script, **kwargs):
        raise AssertionError("fallback must not run when dialogue succeeds")

    monkeypatch.setattr(voices_mod, "synthesize_dialogue", fake_dialogue)
    monkeypatch.setattr(voices_mod, "synthesize_fallback", boom_fallback)

    result = await voices_mod.synthesize_podcast(_script(), cache=cache)
    assert result.voice_path == "dialogue"
    assert result.data == b"DIALOGUEMP3"


def test_script_hash_changes_with_voice_config(monkeypatch: pytest.MonkeyPatch) -> None:
    script = _script()
    first = voices_mod.script_hash(script)
    monkeypatch.setattr(
        "src.services.media.podcast.voices.settings.PODCAST_VOICE_A", "different_voice"
    )
    assert voices_mod.script_hash(script) != first
