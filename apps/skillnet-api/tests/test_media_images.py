"""Unit tests for `services.media.images.generate_image` key gating (no network).

Without a configured key, the call must fail fast (skip straight to LLMError) instead of
spending a real network round-trip on a request guaranteed to fail auth — mirrors the TTS
path's `DialogueUnsupported` pre-check in `podcast/voices.py`.
"""

import pytest

from src.core.exceptions import LLMError
from src.services.media import images as images_mod


@pytest.mark.asyncio
async def test_generate_image_skips_candidates_with_no_key(monkeypatch):
    monkeypatch.setattr(images_mod.settings, "IMAGE_MODEL", "openrouter/some/model")
    monkeypatch.setattr(images_mod.settings, "IMAGE_FALLBACK_MODEL", "gpt-image-1")
    monkeypatch.setattr(images_mod.settings, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(images_mod.settings, "LLM_API_KEY", "")

    called = False

    async def _fake_aimage_generation(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("must not attempt a network call with no configured key")

    monkeypatch.setattr(images_mod.litellm, "aimage_generation", _fake_aimage_generation)

    with pytest.raises(LLMError):
        await images_mod.generate_image("a prompt")

    assert not called


@pytest.mark.asyncio
async def test_generate_image_calls_out_when_key_present(monkeypatch):
    monkeypatch.setattr(images_mod.settings, "IMAGE_MODEL", "openrouter/some/model")
    monkeypatch.setattr(images_mod.settings, "IMAGE_FALLBACK_MODEL", "gpt-image-1")
    monkeypatch.setattr(images_mod.settings, "OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setattr(images_mod.settings, "LLM_API_KEY", "")

    class _Resp:
        data = [{"b64_json": "AAAA"}]

    async def _fake_aimage_generation(**kwargs):
        assert kwargs["api_key"] == "sk-test"
        return _Resp()

    monkeypatch.setattr(images_mod.litellm, "aimage_generation", _fake_aimage_generation)

    result = await images_mod.generate_image("a prompt")
    assert isinstance(result, bytes)
