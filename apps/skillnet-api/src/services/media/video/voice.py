"""Per-slide narration voice — one line becomes one mp3, reusing the podcast path (§2b).

The Video Overview does not stitch a video file (roadmap §2b + §3 trap): the frontend
player sequences the slides and plays each slide's clip in turn. So each narration line is
synthesized on its own, and the reuse rule of §2b ("reuse 2a's TTS, single host") is taken
literally — a one-turn, single-host :class:`PodcastScript` is fed to the podcast's
:func:`~src.services.media.podcast.voices.synthesize_podcast`, so there is exactly one
voice path in the codebase and every slide clip inherits its dialogue-then-fallback
selection **and its per-content-hash cache** (``script_hash`` over the line + voice, so an
identical line is never voiced twice).

Single host: a one-turn script has only speaker ``A``, which the voice layer maps to
``PODCAST_VOICE_A`` — the narrator. No separate video voice config is needed.
"""

from __future__ import annotations

from src.services.media.podcast.script import PodcastFormat, PodcastScript, PodcastTurn
from src.services.media.podcast.voices import (
    PodcastAudioCache,
    SynthesisResult,
    synthesize_podcast,
)
from src.services.media.video.narration import estimate_seconds
from src.services.tts_service import TTSService


def narration_script(text: str, *, language: str) -> PodcastScript:
    """Wrap one narration line as a one-turn, single-host podcast script. Pure.

    ``THE_BRIEF`` is the single-host format, so the whole line is spoken by ``A`` in one
    voice. ``target_seconds`` is a rough estimate — it only shapes the script, never the
    real clip duration the player measures.
    """
    return PodcastScript(
        turns=[PodcastTurn(speaker="A", text=text)],
        format=PodcastFormat.THE_BRIEF,
        language=language,
        target_seconds=estimate_seconds(text),
    )


async def synthesize_narration(
    text: str,
    *,
    language: str = "es",
    cache: PodcastAudioCache | None = None,
    tts: TTSService | None = None,
    allow_dialogue: bool = True,
) -> SynthesisResult:
    """Synthesize one narration line into an mp3, reusing the podcast voice path.

    Returns the bytes and which path produced them (``cache`` / ``dialogue`` / ``fallback``)
    so the generator — and the smoke test — can report the route taken per slide.
    """
    return await synthesize_podcast(
        narration_script(text, language=language),
        cache=cache,
        tts=tts,
        allow_dialogue=allow_dialogue,
    )


__all__ = ["narration_script", "synthesize_narration"]
