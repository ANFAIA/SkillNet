"""Provider-agnostic Text-to-Speech service with disk cache.

Follows the litellm pattern: the admin configures a provider and API key in the
environment (``TTS_PROVIDER``, ``TTS_API_KEY``), and the service abstracts the rest.
Callers see ``TTSService.synthesize`` and get back audio bytes — the provider is an
implementation detail.

Cached on disk by a SHA-256 of (text + voice + provider + language) so the same
utterance is never synthesized twice.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import re
import tempfile
from abc import ABC, abstractmethod
from html import escape
from pathlib import Path
from typing import ClassVar

import httpx

from src.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Abstract provider
# ---------------------------------------------------------------------------


# Language code plus optional variant: "es", "es+m3", "en-us". Nothing else is a voice.
_ESPEAK_VOICE_RE = re.compile(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})?(?:\+[A-Za-z0-9]{1,8})?")

class TTSProvider(ABC):
    """Uniform interface every TTS backend must implement."""

    name: ClassVar[str]
    """Short slug used in cache keys and logs."""
    default_voice: ClassVar[str]
    """Provider-specific voice used when TTS_VOICE is empty."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    @abstractmethod
    async def synthesize(self, text: str, voice: str, language: str) -> bytes:
        """Return raw audio bytes (MP3)."""

    @abstractmethod
    def available_voices(self) -> list[dict[str, str]]:
        """Return ``[{"id": ..., "name": ...}, ...]`` for the configured provider."""


# ---------------------------------------------------------------------------
# OpenAI TTS
# ---------------------------------------------------------------------------


class OpenAITTSProvider(TTSProvider):
    """OpenAI ``tts-1`` / ``tts-1-hd`` via the official async client."""

    name: ClassVar[str] = "openai"
    default_voice: ClassVar[str] = "alloy"

    _VOICES: ClassVar[list[dict[str, str]]] = [
        {"id": "alloy", "name": "Alloy"},
        {"id": "ash", "name": "Ash"},
        {"id": "coral", "name": "Coral"},
        {"id": "echo", "name": "Echo"},
        {"id": "fable", "name": "Fable"},
        {"id": "onyx", "name": "Onyx"},
        {"id": "nova", "name": "Nova"},
        {"id": "sage", "name": "Sage"},
        {"id": "shimmer", "name": "Shimmer"},
    ]

    async def synthesize(self, text: str, voice: str = "alloy", language: str = "es") -> bytes:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.api_key)
        response = await client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text,
        )
        return response.content

    def available_voices(self) -> list[dict[str, str]]:
        return list(self._VOICES)


# ---------------------------------------------------------------------------
# Google Cloud Text-to-Speech (WaveNet)
# ---------------------------------------------------------------------------


class GoogleWaveNetProvider(TTSProvider):
    """Google Cloud WaveNet via ``google-cloud-texttospeech``.

    Requires the ``google-cloud-texttospeech`` package (optional dependency).
    The ``api_key`` is unused when running with Application Default Credentials;
    pass the path to a service-account JSON file instead.
    """

    name: ClassVar[str] = "google"
    default_voice: ClassVar[str] = "es-ES-Wavenet-B"

    _VOICE_MAP: ClassVar[dict[str, str]] = {
        "es-ES-Wavenet-B": "Spanish (Spain) Male",
        "es-ES-Wavenet-C": "Spanish (Spain) Female",
        "es-ES-Wavenet-D": "Spanish (Spain) Male 2",
        "es-US-Wavenet-A": "Spanish (US) Female",
        "es-US-Wavenet-B": "Spanish (US) Male",
        "en-US-Wavenet-D": "English (US) Male",
        "en-US-Wavenet-F": "English (US) Female",
    }

    async def synthesize(
        self, text: str, voice: str = "es-ES-Wavenet-B", language: str = "es",
    ) -> bytes:
        try:
            from google.cloud import texttospeech  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "google-cloud-texttospeech is not installed. "
                "Install it with: pip install google-cloud-texttospeech"
            ) from exc

        import asyncio

        language_code = voice.rsplit("-", 1)[0] if "-" in voice else f"{language}-ES"

        client = texttospeech.TextToSpeechClient()
        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice_params = texttospeech.VoiceSelectionParams(
            language_code=language_code,
            name=voice,
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
        )

        # The sync client in a thread so we do not block the event loop.
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.synthesize_speech(
                input=synthesis_input, voice=voice_params, audio_config=audio_config
            ),
        )
        return response.audio_content

    def available_voices(self) -> list[dict[str, str]]:
        return [{"id": vid, "name": vname} for vid, vname in self._VOICE_MAP.items()]


# ---------------------------------------------------------------------------
# ElevenLabs (stub)
# ---------------------------------------------------------------------------


class ElevenLabsProvider(TTSProvider):
    """ElevenLabs TTS via their REST API (v1).

    Uses ``httpx`` (already a project dependency) — no SDK needed.
    The ``voice`` parameter is an ElevenLabs voice ID. The ``language`` is passed
    as ``language_code`` in the request body so the model picks the right accent.
    """

    name: ClassVar[str] = "elevenlabs"
    default_voice: ClassVar[str] = "21m00Tcm4TlvDq8ikWAM"

    _BASE = "https://api.elevenlabs.io/v1"

    # Curated default voices (multilingual v2 model).
    _VOICES: ClassVar[list[dict[str, str]]] = [
        {"id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel"},
        {"id": "29vD33N1CtxCmqQRPOHJ", "name": "Drew"},
        {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Sarah"},
        {"id": "ErXwobaYiN019PkySvjV", "name": "Antoni"},
        {"id": "MF3mGyEYCl7XYWbV9V6O", "name": "Elli"},
        {"id": "TxGEqnHWrfWFTfGW9XjX", "name": "Josh"},
        {"id": "pNInz6obpgDQGcFmaJgB", "name": "Adam"},
        {"id": "yoZ06aMxZJJ28mfd3POQ", "name": "Sam"},
    ]

    async def synthesize(self, text: str, voice: str = "21m00Tcm4TlvDq8ikWAM", language: str = "es") -> bytes:
        import httpx

        url = f"{self._BASE}/text-to-speech/{voice}"
        headers = {"xi-api-key": self.api_key, "Content-Type": "application/json"}
        body = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            "language_code": language,
        }

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code != 200:
                detail = resp.text[:300]
                raise RuntimeError(f"ElevenLabs API error {resp.status_code}: {detail}")
            return resp.content

    def available_voices(self) -> list[dict[str, str]]:
        return list(self._VOICES)


# ---------------------------------------------------------------------------
# Microsoft Azure AI Speech
# ---------------------------------------------------------------------------


class AzureSpeechProvider(TTSProvider):
    """Microsoft Azure AI Speech through its REST API."""

    name: ClassVar[str] = "azure"
    default_voice: ClassVar[str] = "es-ES-ElviraNeural"

    _VOICES: ClassVar[list[dict[str, str]]] = [
        {"id": "es-ES-ElviraNeural", "name": "Elvira (Spanish, Spain)"},
        {"id": "es-ES-AlvaroNeural", "name": "Álvaro (Spanish, Spain)"},
        {"id": "es-MX-DaliaNeural", "name": "Dalia (Spanish, Mexico)"},
        {"id": "es-MX-JorgeNeural", "name": "Jorge (Spanish, Mexico)"},
        {"id": "es-US-PalomaNeural", "name": "Paloma (Spanish, United States)"},
        {"id": "es-US-AlonsoNeural", "name": "Alonso (Spanish, United States)"},
    ]
    _LANGUAGE_CODES: ClassVar[dict[str, str]] = {
        "es": "es-ES",
        "en": "en-US",
        "fr": "fr-FR",
        "de": "de-DE",
        "it": "it-IT",
        "pt": "pt-PT",
    }

    def __init__(
        self,
        api_key: str,
        *,
        region: str,
        endpoint: str,
        timeout_seconds: float,
    ) -> None:
        super().__init__(api_key)
        if not api_key:
            raise ValueError("Azure Speech requires TTS_API_KEY")
        if not region.strip():
            raise ValueError("Azure Speech requires TTS_AZURE_REGION")
        if not endpoint.strip():
            raise ValueError("Azure Speech requires TTS_AZURE_ENDPOINT")
        self.region = region.strip()
        self.endpoint = endpoint.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def synthesize(
        self,
        text: str,
        voice: str = default_voice,
        language: str = "es",
    ) -> bytes:
        language_code = self._LANGUAGE_CODES.get(language, language)
        ssml = (
            f'<speak version="1.0" xml:lang="{escape(language_code, quote=True)}">'
            f'<voice name="{escape(voice, quote=True)}">{escape(text)}</voice>'
            "</speak>"
        )
        headers = {
            "Ocp-Apim-Subscription-Key": self.api_key,
            "Ocp-Apim-Subscription-Region": self.region,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
            "User-Agent": "SkillNet",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    self.endpoint,
                    headers=headers,
                    content=ssml.encode("utf-8"),
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise RuntimeError("Azure Speech request timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Azure Speech request failed with status {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError("Azure Speech request could not be completed") from exc
        return response.content

    def available_voices(self) -> list[dict[str, str]]:
        return list(self._VOICES)


# ---------------------------------------------------------------------------
# Offline eSpeak NG (no key, no quota — the last-resort fallback)
# ---------------------------------------------------------------------------


class EspeakOfflineProvider(TTSProvider):
    """Offline TTS via the ``espeak-ng`` binary, so a deployment with no paid TTS key or
    quota still produces a *real* spoken-audio file rather than failing the whole job.

    Robotic, not broadcast quality — it is the safety net beneath the cloud providers, not
    a replacement for them. Renders to WAV with ``espeak-ng`` and transcodes to MP3 with
    ``ffmpeg`` (already on the image), so its output slots into the same mp3 pipeline
    (concat, cache, asset store) as every other provider. Needs neither ``api_key`` nor
    network. ``voice`` is an espeak voice/variant spec (e.g. ``es+m3``); it falls back to
    the language's base voice when empty.
    """

    name: ClassVar[str] = "offline"
    default_voice: ClassVar[str] = "es"

    _VOICES: ClassVar[list[dict[str, str]]] = [
        {"id": "es+m3", "name": "Español (voz masculina)"},
        {"id": "es+f3", "name": "Español (voz femenina)"},
    ]

    def __init__(self, api_key: str = "") -> None:  # noqa: D107 - no key needed
        super().__init__(api_key)

    async def synthesize(self, text: str, voice: str = default_voice, language: str = "es") -> bytes:
        import asyncio

        espeak = shutil.which("espeak-ng") or shutil.which("espeak")
        if espeak is None:
            raise RuntimeError("espeak-ng not found on PATH; offline TTS unavailable")
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise RuntimeError("ffmpeg not found on PATH; cannot transcode offline audio")
        voice_spec = voice or (language if "-" not in language else language.split("-")[0]) or "es"
        # `voice` reaches here straight from the request: `_resolve_voice` in routes/tts.py
        # passes unknown values through, so it is attacker-controlled and lands in argv.
        # An espeak voice spec is a language code with optional variant ("es", "es+m3",
        # "en-us"); anything else is not a voice and must not become an option.
        if not _ESPEAK_VOICE_RE.fullmatch(voice_spec):
            voice_spec = "es"

        def _run() -> bytes:
            with tempfile.TemporaryDirectory() as tmp:
                wav = os.path.join(tmp, "out.wav")
                mp3 = os.path.join(tmp, "out.mp3")
                speak = subprocess.run(
                    # `--` terminates option parsing, and it is load-bearing, not style.
                    # espeak-ng parses with getopt_long, which PERMUTES arguments: without
                    # the terminator a `text` beginning with a dash is read as an option,
                    # not as words to speak. `{"text": "-f/proc/self/environ"}` posted to
                    # /api/v1/tts/synthesize then returned an mp3 reading the container's
                    # environment aloud — SECRET_KEY, LLM_API_KEY and the database
                    # password. Any authenticated user could reach it, because this
                    # provider is the automatic fallback whenever the paid one fails.
                    [espeak, "-v", voice_spec, "-s", "155", "-w", wav, "--", text],
                    capture_output=True,
                )
                if speak.returncode != 0:
                    detail = speak.stderr.decode("utf-8", "replace")[-300:]
                    raise RuntimeError(f"espeak-ng failed ({speak.returncode}): {detail}")
                trans = subprocess.run(
                    [ffmpeg, "-y", "-i", wav, "-c:a", "libmp3lame", "-q:a", "5", mp3],
                    capture_output=True,
                )
                if trans.returncode != 0:
                    detail = trans.stderr.decode("utf-8", "replace")[-300:]
                    raise RuntimeError(f"ffmpeg transcode failed ({trans.returncode}): {detail}")
                return Path(mp3).read_bytes()

        return await asyncio.get_running_loop().run_in_executor(None, _run)

    def available_voices(self) -> list[dict[str, str]]:
        return list(self._VOICES)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_PROVIDERS: dict[str, type[TTSProvider]] = {
    "openai": OpenAITTSProvider,
    "google": GoogleWaveNetProvider,
    "elevenlabs": ElevenLabsProvider,
    "azure": AzureSpeechProvider,
    "offline": EspeakOfflineProvider,
}


def get_tts_provider(
    provider_name: str,
    api_key: str,
    *,
    azure_region: str | None = None,
    azure_endpoint: str | None = None,
    timeout_seconds: float | None = None,
) -> TTSProvider:
    """Instantiate the right provider from a short name.

    Raises ``ValueError`` for unknown or disabled providers.
    """
    if provider_name == "disabled":
        raise ValueError("TTS is disabled in this deployment")
    cls = _PROVIDERS.get(provider_name)
    if cls is None:
        raise ValueError(
            f"Unknown TTS provider {provider_name!r}. "
            f"Available: {', '.join(_PROVIDERS)}"
        )
    if cls is AzureSpeechProvider:
        return cls(
            api_key=api_key,
            region=azure_region if azure_region is not None else settings.TTS_AZURE_REGION,
            endpoint=(
                azure_endpoint
                if azure_endpoint is not None
                else settings.TTS_AZURE_ENDPOINT
            ),
            timeout_seconds=(
                timeout_seconds
                if timeout_seconds is not None
                else settings.TTS_TIMEOUT_SECONDS
            ),
        )
    return cls(api_key=api_key)


# ---------------------------------------------------------------------------
# Disk cache
# ---------------------------------------------------------------------------


def _cache_key(text: str, voice: str, provider: str, language: str) -> str:
    material = f"{text}|{voice}|{provider}|{language}"
    return hashlib.sha256(material.encode()).hexdigest()


class TTSCache:
    """Simple file-system cache keyed by content hash."""

    def __init__(self, cache_dir: str | Path | None = None) -> None:
        self.cache_dir = Path(cache_dir or settings.TTS_CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.mp3"

    def get(self, text: str, voice: str, provider: str, language: str) -> bytes | None:
        path = self._path(_cache_key(text, voice, provider, language))
        if path.exists():
            logger.debug("TTS cache hit: %s", path.name)
            return path.read_bytes()
        return None

    def put(self, text: str, voice: str, provider: str, language: str, audio: bytes) -> Path:
        key = _cache_key(text, voice, provider, language)
        cache_path = self._path(key)
        # Atomic write: write to temp file then rename to avoid partial reads
        # from concurrent requests.
        fd, tmp_path = tempfile.mkstemp(dir=str(self.cache_dir))
        closed = False
        try:
            os.write(fd, audio)
            os.close(fd)
            closed = True
            os.replace(tmp_path, str(cache_path))
        except BaseException:
            if not closed:
                os.close(fd)
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        logger.debug("TTS cache store: %s (%d bytes)", cache_path.name, len(audio))
        return cache_path


# ---------------------------------------------------------------------------
# High-level service
# ---------------------------------------------------------------------------


class TTSService:
    """Synthesize speech through the configured provider, with disk caching."""

    def __init__(
        self,
        provider: TTSProvider | None = None,
        cache: TTSCache | None = None,
    ) -> None:
        self.provider = provider or get_tts_provider(
            settings.TTS_PROVIDER,
            settings.TTS_API_KEY,
        )
        self.cache = cache or TTSCache()

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        language: str | None = None,
    ) -> bytes:
        voice = voice or settings.TTS_VOICE or self.provider.default_voice
        language = language or settings.TTS_LANGUAGE

        cached = self.cache.get(text, voice, self.provider.name, language)
        if cached is not None:
            return cached

        audio = await self.provider.synthesize(text, voice, language)
        self.cache.put(text, voice, self.provider.name, language, audio)
        return audio

    def available_voices(self) -> list[dict[str, str]]:
        return self.provider.available_voices()
