"""TTS service: provider factory, disk cache, and synthesis pipeline.

No network, no DB. Provider calls are mocked.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.services.tts_service import (
    ElevenLabsProvider,
    GoogleWaveNetProvider,
    OpenAITTSProvider,
    TTSCache,
    TTSProvider,
    TTSService,
    get_tts_provider,
)

# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------


class TestGetTTSProvider:
    def test_returns_openai_provider(self):
        provider = get_tts_provider("openai", "sk-test")
        assert isinstance(provider, OpenAITTSProvider)
        assert provider.api_key == "sk-test"

    def test_returns_google_provider(self):
        provider = get_tts_provider("google", "key")
        assert isinstance(provider, GoogleWaveNetProvider)

    def test_returns_elevenlabs_provider(self):
        provider = get_tts_provider("elevenlabs", "key")
        assert isinstance(provider, ElevenLabsProvider)

    def test_disabled_raises(self):
        with pytest.raises(ValueError, match="disabled"):
            get_tts_provider("disabled", "")

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown TTS provider"):
            get_tts_provider("nonexistent", "key")


# ---------------------------------------------------------------------------
# Available voices
# ---------------------------------------------------------------------------


class TestAvailableVoices:
    def test_openai_voices_are_non_empty(self):
        provider = OpenAITTSProvider(api_key="test")
        voices = provider.available_voices()
        assert len(voices) > 0
        assert all("id" in v and "name" in v for v in voices)

    def test_google_voices_are_non_empty(self):
        provider = GoogleWaveNetProvider(api_key="test")
        voices = provider.available_voices()
        assert len(voices) > 0

    def test_elevenlabs_voices_are_non_empty(self):
        provider = ElevenLabsProvider(api_key="test")
        voices = provider.available_voices()
        assert len(voices) >= 1


# ---------------------------------------------------------------------------
# Disk cache
# ---------------------------------------------------------------------------


class TestTTSCache:
    def test_miss_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = TTSCache(cache_dir=tmp)
            result = cache.get("hello", "alloy", "openai", "es")
            assert result is None

    def test_put_then_get_returns_same_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = TTSCache(cache_dir=tmp)
            audio = b"\xff\xfb\x90\x00" * 100  # fake MP3 bytes
            cache.put("hello", "alloy", "openai", "es", audio)
            result = cache.get("hello", "alloy", "openai", "es")
            assert result == audio

    def test_different_text_is_a_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = TTSCache(cache_dir=tmp)
            cache.put("hello", "alloy", "openai", "es", b"audio1")
            result = cache.get("goodbye", "alloy", "openai", "es")
            assert result is None

    def test_different_voice_is_a_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = TTSCache(cache_dir=tmp)
            cache.put("hello", "alloy", "openai", "es", b"audio1")
            result = cache.get("hello", "nova", "openai", "es")
            assert result is None

    def test_different_provider_is_a_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = TTSCache(cache_dir=tmp)
            cache.put("hello", "alloy", "openai", "es", b"audio1")
            result = cache.get("hello", "alloy", "google", "es")
            assert result is None

    def test_different_language_is_a_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = TTSCache(cache_dir=tmp)
            cache.put("hello", "alloy", "openai", "es", b"audio1")
            result = cache.get("hello", "alloy", "openai", "en")
            assert result is None

    def test_put_creates_mp3_file_on_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = TTSCache(cache_dir=tmp)
            cache.put("hello", "alloy", "openai", "es", b"audio")
            files = list(Path(tmp).glob("*.mp3"))
            assert len(files) == 1

    def test_cache_dir_created_if_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "a" / "b" / "c"
            cache = TTSCache(cache_dir=nested)
            assert nested.exists()
            cache.put("hello", "alloy", "openai", "es", b"audio")
            assert cache.get("hello", "alloy", "openai", "es") == b"audio"


# ---------------------------------------------------------------------------
# TTSService integration (mocked provider)
# ---------------------------------------------------------------------------


class _FakeProvider(TTSProvider):
    """In-memory provider for testing the service pipeline."""

    name = "fake"

    def __init__(self) -> None:
        super().__init__(api_key="")
        self.synthesize_mock = AsyncMock(return_value=b"fake-audio-bytes")

    async def synthesize(self, text: str, voice: str, language: str) -> bytes:
        return await self.synthesize_mock(text, voice, language)

    def available_voices(self) -> list[dict[str, str]]:
        return [{"id": "v1", "name": "Voice 1"}]


class TestTTSService:
    async def test_synthesize_calls_provider_on_cache_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = _FakeProvider()
            cache = TTSCache(cache_dir=tmp)
            service = TTSService(provider=provider, cache=cache)

            result = await service.synthesize("hello world", voice="v1", language="es")

            assert result == b"fake-audio-bytes"
            provider.synthesize_mock.assert_awaited_once_with("hello world", "v1", "es")

    async def test_synthesize_returns_cached_without_calling_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = _FakeProvider()
            cache = TTSCache(cache_dir=tmp)
            service = TTSService(provider=provider, cache=cache)

            # First call: populates cache
            await service.synthesize("hello", voice="v1", language="es")
            # Second call: should be from cache
            result = await service.synthesize("hello", voice="v1", language="es")

            assert result == b"fake-audio-bytes"
            assert provider.synthesize_mock.await_count == 1  # only once

    async def test_available_voices_delegates_to_provider(self):
        provider = _FakeProvider()
        service = TTSService(provider=provider, cache=TTSCache(cache_dir=tempfile.mkdtemp()))
        voices = service.available_voices()
        assert voices == [{"id": "v1", "name": "Voice 1"}]

    async def test_service_uses_settings_defaults_for_voice_and_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = _FakeProvider()
            cache = TTSCache(cache_dir=tmp)
            service = TTSService(provider=provider, cache=cache)

            with patch("src.services.tts_service.settings") as mock_settings:
                mock_settings.TTS_VOICE = "default-voice"
                mock_settings.TTS_LANGUAGE = "en"
                await service.synthesize("hi")

            provider.synthesize_mock.assert_awaited_once_with("hi", "default-voice", "en")


# ---------------------------------------------------------------------------
# ElevenLabs provider (mocked HTTP)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, content: bytes = b"", text: str = "") -> None:
        self.status_code = status_code
        self.content = content
        self.text = text


class _FakeAsyncClient:
    """Stands in for ``httpx.AsyncClient`` so the provider never hits the network."""

    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.calls: list[dict[str, object]] = []

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def post(self, url: str, headers: dict | None = None, json: dict | None = None) -> _FakeResponse:
        self.calls.append({"url": url, "headers": headers, "json": json})
        return self._response


class TestElevenLabsProvider:
    async def test_synthesize_posts_to_the_voice_endpoint_and_returns_the_audio(self):
        client = _FakeAsyncClient(_FakeResponse(200, content=b"audio-bytes"))

        with patch("httpx.AsyncClient", return_value=client):
            audio = await ElevenLabsProvider(api_key="secret").synthesize("hola", "voice-id", "es")

        assert audio == b"audio-bytes"
        call = client.calls[0]
        # The voice ID belongs in the path, not the body — a voice in the body is
        # silently ignored by ElevenLabs and you get the default voice instead.
        assert str(call["url"]).endswith("/text-to-speech/voice-id")
        assert call["headers"]["xi-api-key"] == "secret"  # type: ignore[index]
        assert call["json"]["text"] == "hola"  # type: ignore[index]
        assert call["json"]["language_code"] == "es"  # type: ignore[index]
        assert call["json"]["model_id"] == "eleven_multilingual_v2"  # type: ignore[index]

    async def test_a_failed_request_raises_with_the_provider_detail(self):
        client = _FakeAsyncClient(_FakeResponse(401, text="invalid api key"))

        with patch("httpx.AsyncClient", return_value=client):
            with pytest.raises(RuntimeError, match="401") as err:
                await ElevenLabsProvider(api_key="bad").synthesize("hola", "voice-id", "es")

        # The provider's own message is what tells you it is the key and not the
        # voice, so it has to survive into the error.
        assert "invalid api key" in str(err.value)

    def test_voices_are_non_empty_and_shaped_like_the_other_providers(self):
        voices = ElevenLabsProvider(api_key="test").available_voices()
        assert len(voices) > 0
        assert all("id" in v and "name" in v for v in voices)
