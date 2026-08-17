"""Voice synthesis for the podcast: a validated script becomes one mp3 (roadmap §2a).

Two paths, chosen at runtime:

* **Primary — ElevenLabs Text-to-Dialogue.** One call turns the whole multi-speaker script
  into a single, naturally-timed mp3 (``client.text_to_dialogue.convert(inputs=[...],
  model_id="eleven_v3")``). This is what makes it sound like a real two-host show rather
  than two monologues stitched together. It needs a recent ``elevenlabs`` SDK and an
  account/plan that exposes the endpoint.
* **Fallback — per-turn TTS + ffmpeg concat.** When the SDK or the endpoint is not
  available, each turn is synthesized separately through the **existing**
  :class:`~src.services.tts_service.TTSService` (so there is exactly one ElevenLabs client
  path in the codebase, the REST one) and the segments are concatenated with ffmpeg, which
  is already on the image.

The result is cached by ``content_hash(script_json)`` so the same script is never
synthesized twice — the expensive, quota-consuming step. Cache and bytes both live under
the media assets dir; the spine's :class:`AssetStore` still content-addresses the final mp3
when the generator returns it.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from src.config import settings
from src.core.logging import get_logger
from src.services.media.podcast.script import PodcastScript
from src.services.tts_service import TTSService

logger = get_logger(__name__)

VoicePath = Literal["dialogue", "fallback", "cache"]


class DialogueUnsupported(RuntimeError):
    """Raised when the ElevenLabs Text-to-Dialogue path is not usable in this deployment.

    Not an error the caller should surface — it is the signal to take the fallback path.
    Carries the reason (no SDK, old SDK, endpoint absent) for the logs and the smoke test.
    """


@dataclass(frozen=True)
class SynthesisResult:
    """What synthesis produced: the mp3 bytes and which path made them."""

    data: bytes
    ext: str
    voice_path: VoicePath


def script_hash(script: PodcastScript) -> str:
    """A stable SHA-256 over the script + the voice ids + the model that will speak it.

    The voices and the dialogue model are part of the key because the same words in a
    different voice are a different mp3; changing ``PODCAST_VOICE_A`` must miss the cache.
    """
    material = {
        "turns": [t.model_dump() for t in script.turns],
        "format": script.format.value,
        "language": script.language,
        "voice_a": settings.PODCAST_VOICE_A,
        "voice_b": settings.PODCAST_VOICE_B,
        "model": settings.PODCAST_DIALOGUE_MODEL,
    }
    blob = json.dumps(material, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


class PodcastAudioCache:
    """Disk cache of finished episodes, keyed by :func:`script_hash`.

    Distinct from the content-addressed :class:`AssetStore` (which keys by the mp3 bytes):
    this one lets us skip synthesis entirely — the point being to not spend ElevenLabs
    quota re-rendering a script we already voiced.
    """

    def __init__(self, base_dir: str | Path | None = None) -> None:
        root = Path(base_dir or settings.MEDIA_ASSETS_DIR) / "podcast_cache"
        root.mkdir(parents=True, exist_ok=True)
        self.base_dir = root

    def _path(self, digest: str) -> Path:
        return self.base_dir / f"{digest}.mp3"

    def get(self, digest: str) -> bytes | None:
        path = self._path(digest)
        if path.exists():
            logger.debug("Podcast audio cache hit: %s", path.name)
            return path.read_bytes()
        return None

    def put(self, digest: str, data: bytes) -> None:
        path = self._path(digest)
        fd, tmp = tempfile.mkstemp(dir=str(self.base_dir))
        closed = False
        try:
            os.write(fd, data)
            os.close(fd)
            closed = True
            os.replace(tmp, str(path))
        except BaseException:
            if not closed:
                os.close(fd)
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise


# --------------------------------------------------------------------------------------
# Primary path: ElevenLabs Text-to-Dialogue (one call -> one mp3)
# --------------------------------------------------------------------------------------
def _load_dialogue_sdk() -> tuple[type, type]:
    """Return ``(ElevenLabs, DialogueInput)`` or raise :class:`DialogueUnsupported`.

    Detection is by import: the SDK moves these symbols around across versions, so several
    known locations are tried before concluding the path is unavailable.
    """
    try:
        from elevenlabs.client import ElevenLabs
    except Exception as exc:  # noqa: BLE001 - any import failure means "not available"
        raise DialogueUnsupported(f"elevenlabs SDK not importable: {exc}") from exc

    dialogue_input: type | None = None
    for module_path, name in (
        ("elevenlabs.types", "DialogueInput"),
        ("elevenlabs", "DialogueInput"),
    ):
        try:
            module = __import__(module_path, fromlist=[name])
            dialogue_input = getattr(module, name, None)
        except Exception:  # noqa: BLE001 - keep trying the next known location
            dialogue_input = None
        if dialogue_input is not None:
            break

    if dialogue_input is None:
        raise DialogueUnsupported("elevenlabs SDK has no DialogueInput type")
    return ElevenLabs, dialogue_input


def _voice_for(speaker: str) -> str:
    return settings.PODCAST_VOICE_A if speaker == "A" else settings.PODCAST_VOICE_B


async def synthesize_dialogue(script: PodcastScript) -> bytes:
    """Primary path. One Text-to-Dialogue call for the whole script -> mp3 bytes.

    Raises :class:`DialogueUnsupported` if the SDK/endpoint is not there (the caller then
    falls back). The SDK is synchronous, so the call runs in a worker thread to keep the
    event loop free.
    """
    eleven_cls, dialogue_input_cls = _load_dialogue_sdk()
    api_key = settings.TTS_API_KEY
    if not api_key:
        raise DialogueUnsupported("no TTS_API_KEY configured for ElevenLabs")

    inputs = [
        dialogue_input_cls(text=turn.text, voice_id=_voice_for(turn.speaker))
        for turn in script.turns
    ]

    def _run() -> bytes:
        client = eleven_cls(api_key=api_key)
        endpoint = getattr(client, "text_to_dialogue", None)
        if endpoint is None or not hasattr(endpoint, "convert"):
            raise DialogueUnsupported("elevenlabs client has no text_to_dialogue.convert")
        audio = endpoint.convert(inputs=inputs, model_id=settings.PODCAST_DIALOGUE_MODEL)
        if isinstance(audio, (bytes, bytearray)):
            return bytes(audio)
        # convert() usually returns a generator of byte chunks.
        return b"".join(audio)

    return await asyncio.get_running_loop().run_in_executor(None, _run)


# --------------------------------------------------------------------------------------
# Fallback path: per-turn TTS through the existing service, concatenated with ffmpeg
# --------------------------------------------------------------------------------------
def _ffmpeg_bin() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg not found on PATH; cannot concatenate audio segments")
    return ffmpeg


def concat_mp3_segments(segments: list[bytes]) -> bytes:
    """Join mp3 byte segments into one mp3 via ffmpeg's concat demuxer (re-encoding).

    Re-encoding (``libmp3lame``) rather than stream-copy so segments with slightly
    different headers/parameters — which per-call TTS output routinely has — join cleanly
    instead of producing a glitchy or unseekable file. A single segment is returned as-is.
    """
    if not segments:
        raise ValueError("no audio segments to concatenate")
    if len(segments) == 1:
        return segments[0]

    ffmpeg = _ffmpeg_bin()
    with tempfile.TemporaryDirectory() as tmpdir:
        paths: list[str] = []
        for index, seg in enumerate(segments):
            seg_path = os.path.join(tmpdir, f"seg{index:03d}.mp3")
            with open(seg_path, "wb") as handle:
                handle.write(seg)
            paths.append(seg_path)

        list_path = os.path.join(tmpdir, "concat.txt")
        with open(list_path, "w", encoding="utf-8") as handle:
            for path in paths:
                # ffmpeg's concat list wants forward slashes even on Windows.
                handle.write(f"file '{path.replace(os.sep, '/')}'\n")

        out_path = os.path.join(tmpdir, "out.mp3")
        result = subprocess.run(
            [
                ffmpeg, "-y",
                "-f", "concat", "-safe", "0",
                "-i", list_path,
                "-c:a", "libmp3lame", "-q:a", "4",
                out_path,
            ],
            capture_output=True,
        )
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", "replace")[-500:]
            raise RuntimeError(f"ffmpeg concat failed ({result.returncode}): {detail}")
        return Path(out_path).read_bytes()


@dataclass(frozen=True)
class _FallbackVoice:
    """One fallback TTS provider plus the two host voices it should speak A/B with."""

    service: TTSService
    voice_a: str
    voice_b: str

    def voice_for(self, speaker: str) -> str:
        return self.voice_a if speaker == "A" else self.voice_b


def _build_fallback_chain(tts: TTSService | None) -> list[_FallbackVoice]:
    """The ordered per-turn TTS fallbacks, richest first, ending in an offline safety net.

    1. The **configured** provider (``TTS_PROVIDER`` — ElevenLabs here), spoken with the
       two ElevenLabs host voices. This is the same client path ``/tts`` uses.
    2. **Azure AI Speech**, but only when its region+endpoint+key are actually configured
       (the owner-offered fallback). Spoken with two Spanish Azure neural voices.
    3. **Offline eSpeak NG** — no key, no quota, always last. Guarantees the pipeline still
       produces a *real* spoken-audio mp3 when every cloud provider is unavailable or out
       of quota, instead of failing the whole job.
    """
    from src.services.tts_service import (
        EspeakOfflineProvider,
        get_tts_provider,
    )

    chain: list[_FallbackVoice] = []

    # 1. The configured provider (injectable for tests).
    if tts is not None:
        chain.append(
            _FallbackVoice(tts, settings.PODCAST_VOICE_A, settings.PODCAST_VOICE_B)
        )
    elif settings.TTS_PROVIDER and settings.TTS_PROVIDER != "disabled":
        try:
            chain.append(
                _FallbackVoice(
                    TTSService(),
                    settings.PODCAST_VOICE_A,
                    settings.PODCAST_VOICE_B,
                )
            )
        except Exception as exc:  # noqa: BLE001 - a mis-configured provider must not block the chain
            logger.info("Configured TTS provider unavailable for podcast: %s", exc)

    # 2. Azure, only when it is genuinely configured.
    if (
        settings.TTS_API_KEY
        and settings.TTS_AZURE_REGION.strip()
        and settings.TTS_AZURE_ENDPOINT.strip()
        and settings.TTS_PROVIDER != "azure"  # already covered above
    ):
        try:
            azure = TTSService(provider=get_tts_provider("azure", settings.TTS_API_KEY))
            chain.append(
                _FallbackVoice(azure, "es-ES-AlvaroNeural", "es-ES-ElviraNeural")
            )
        except Exception as exc:  # noqa: BLE001 - configured but unusable; skip it
            logger.info("Azure TTS fallback unavailable: %s", exc)

    # 3. Offline eSpeak NG — the always-present safety net.
    chain.append(
        _FallbackVoice(
            TTSService(provider=EspeakOfflineProvider()), "es+m3", "es+f3"
        )
    )
    return chain


async def synthesize_fallback(
    script: PodcastScript, *, tts: TTSService | None = None
) -> bytes:
    """Fallback path. Synthesize each turn through a chain of TTS providers, then concat.

    Tries each provider in :func:`_build_fallback_chain` for the whole script; the first
    that voices every turn wins. A provider that fails (no quota, bad key, network) is
    logged and the next is tried, so a deployment whose paid provider is exhausted still
    gets a real mp3 from the offline eSpeak safety net. ffmpeg glues the per-turn segments
    into one episode.
    """
    chain = _build_fallback_chain(tts)
    last_exc: Exception | None = None
    for fv in chain:
        try:
            segments: list[bytes] = []
            for turn in script.turns:
                audio = await fv.service.synthesize(
                    turn.text,
                    voice=fv.voice_for(turn.speaker),
                    language=script.language,
                )
                segments.append(audio)
            if fv.service.provider.name != settings.TTS_PROVIDER:
                logger.info("Podcast voiced via fallback provider %s", fv.service.provider.name)
            # Concatenation is CPU/subprocess work: off the event loop.
            return await asyncio.get_running_loop().run_in_executor(
                None, concat_mp3_segments, segments
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - try the next provider in the chain
            last_exc = exc
            logger.warning(
                "Podcast TTS provider %s failed, trying next: %s",
                getattr(fv.service.provider, "name", "?"),
                exc,
            )
    raise RuntimeError(
        f"All podcast TTS providers failed; last error: {last_exc}"
    )


# --------------------------------------------------------------------------------------
# The public entry point
# --------------------------------------------------------------------------------------
async def synthesize_podcast(
    script: PodcastScript,
    *,
    cache: PodcastAudioCache | None = None,
    tts: TTSService | None = None,
    allow_dialogue: bool = True,
) -> SynthesisResult:
    """Turn a script into an mp3, cached by script hash, dialogue-first then fallback.

    Returns the bytes and which path produced them (``cache`` / ``dialogue`` / ``fallback``)
    so callers — and the smoke test — can report the route taken.
    """
    cache = cache or PodcastAudioCache()
    digest = script_hash(script)

    cached = cache.get(digest)
    if cached is not None:
        return SynthesisResult(data=cached, ext="mp3", voice_path="cache")

    voice_path: VoicePath = "fallback"
    data: bytes | None = None
    if allow_dialogue:
        try:
            data = await synthesize_dialogue(script)
            voice_path = "dialogue"
        except DialogueUnsupported as exc:
            logger.info("Podcast dialogue path unavailable, using fallback: %s", exc)
        except Exception as exc:  # noqa: BLE001 - a dialogue failure must not cost the mp3
            logger.warning("Podcast dialogue path failed, using fallback: %s", exc)

    if data is None:
        data = await synthesize_fallback(script, tts=tts)
        voice_path = "fallback"

    if not data:
        raise RuntimeError("voice synthesis produced no audio bytes")

    cache.put(digest, data)
    return SynthesisResult(data=data, ext="mp3", voice_path=voice_path)


__all__ = [
    "VoicePath",
    "DialogueUnsupported",
    "SynthesisResult",
    "script_hash",
    "PodcastAudioCache",
    "synthesize_dialogue",
    "concat_mp3_segments",
    "synthesize_fallback",
    "synthesize_podcast",
]
