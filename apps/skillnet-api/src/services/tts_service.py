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
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from src.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Abstract provider
# ---------------------------------------------------------------------------


class TTSProvider(ABC):
    """Uniform interface every TTS backend must implement."""

    name: ClassVar[str]
    """Short slug used in cache keys and logs."""

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
    """ElevenLabs TTS provider.

    TODO: implement with the ``elevenlabs`` SDK once the dependency is added.
    """

    name: ClassVar[str] = "elevenlabs"

    async def synthesize(self, text: str, voice: str = "default", language: str = "es") -> bytes:
        raise NotImplementedError("ElevenLabs provider is not yet implemented")

    def available_voices(self) -> list[dict[str, str]]:
        return [{"id": "default", "name": "Default (not implemented)"}]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_PROVIDERS: dict[str, type[TTSProvider]] = {
    "openai": OpenAITTSProvider,
    "google": GoogleWaveNetProvider,
    "elevenlabs": ElevenLabsProvider,
}


def get_tts_provider(provider_name: str, api_key: str) -> TTSProvider:
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
        self.provider = provider or get_tts_provider(settings.TTS_PROVIDER, settings.TTS_API_KEY)
        self.cache = cache or TTSCache()

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        language: str | None = None,
    ) -> bytes:
        voice = voice or settings.TTS_VOICE
        language = language or settings.TTS_LANGUAGE

        cached = self.cache.get(text, voice, self.provider.name, language)
        if cached is not None:
            return cached

        audio = await self.provider.synthesize(text, voice, language)
        self.cache.put(text, voice, self.provider.name, language, audio)
        return audio

    def available_voices(self) -> list[dict[str, str]]:
        return self.provider.available_voices()
