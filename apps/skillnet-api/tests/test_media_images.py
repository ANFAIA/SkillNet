"""Unit tests for `services.media.images` — key resolution and key gating (no network).

Two things live here. **Key resolution** (`api_key_for`) is the single function that decides
which key an image model authenticates with; `services.capabilities` imports it rather than
mirroring it, so this is also the test that keeps the capability read honest. **Key gating**:
without a configured key the call must fail fast (straight to LLMError) instead of spending
a real network round-trip on a request guaranteed to fail auth — mirrors the TTS path's
`DialogueUnsupported` pre-check in `podcast/voices.py`.
"""

import pytest

from src.core.exceptions import LLMError
from src.schemas.capabilities import CapabilityReason
from src.services import provider_health
from src.services.media import images as images_mod


@pytest.fixture(autouse=True)
def _clean_health():
    provider_health.reset()
    yield
    provider_health.reset()


@pytest.fixture(autouse=True)
def _no_image_key_override(monkeypatch):
    """Most cases exercise the per-model rule; the override is opted into explicitly."""
    monkeypatch.setattr(images_mod.settings, "IMAGE_API_KEY", "")


def test_image_api_key_wins_over_every_per_model_rule(monkeypatch):
    monkeypatch.setattr(images_mod.settings, "IMAGE_API_KEY", "img-key")
    monkeypatch.setattr(images_mod.settings, "OPENROUTER_API_KEY", "or-key")
    monkeypatch.setattr(images_mod.settings, "LLM_API_KEY", "llm-key")

    assert images_mod.api_key_for("openrouter/google/gemini-2.5-flash-image") == "img-key"
    assert images_mod.api_key_for("gpt-image-1") == "img-key"


def test_an_openrouter_model_falls_back_to_the_openrouter_key(monkeypatch):
    monkeypatch.setattr(images_mod.settings, "OPENROUTER_API_KEY", "or-key")
    monkeypatch.setattr(images_mod.settings, "LLM_API_KEY", "llm-key")

    assert images_mod.api_key_for("openrouter/google/gemini-2.5-flash-image") == "or-key"


def test_any_other_model_falls_back_to_the_llm_key(monkeypatch):
    monkeypatch.setattr(images_mod.settings, "OPENROUTER_API_KEY", "or-key")
    monkeypatch.setattr(images_mod.settings, "LLM_API_KEY", "llm-key")

    assert images_mod.api_key_for("gpt-image-1") == "llm-key"


def test_no_key_at_all_resolves_to_none(monkeypatch):
    monkeypatch.setattr(images_mod.settings, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(images_mod.settings, "LLM_API_KEY", "")

    assert images_mod.api_key_for("gpt-image-1") is None
    assert not images_mod.images_are_available()


def test_availability_follows_the_models_that_will_actually_be_tried(monkeypatch):
    """The fallback is attempted, so a key that only it can use still counts."""
    monkeypatch.setattr(images_mod.settings, "IMAGE_MODEL", "openrouter/some/model")
    monkeypatch.setattr(images_mod.settings, "IMAGE_FALLBACK_MODEL", "gpt-image-1")
    monkeypatch.setattr(images_mod.settings, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(images_mod.settings, "LLM_API_KEY", "llm-key")

    assert images_mod.images_are_available()

    monkeypatch.setattr(images_mod.settings, "IMAGE_FALLBACK_MODEL", "")
    assert not images_mod.images_are_available()


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


@pytest.mark.asyncio
async def test_a_provider_failure_is_recorded_against_the_image_provider(monkeypatch):
    """A key that is present but out of quota is invisible to the config read."""
    monkeypatch.setattr(images_mod.settings, "IMAGE_MODEL", "openrouter/some/model")
    monkeypatch.setattr(images_mod.settings, "IMAGE_FALLBACK_MODEL", "")
    monkeypatch.setattr(images_mod.settings, "OPENROUTER_API_KEY", "sk-test")

    class _RateLimited(Exception):
        status_code = 429

    async def _fake_aimage_generation(**kwargs):
        raise _RateLimited("quota")

    monkeypatch.setattr(images_mod.litellm, "aimage_generation", _fake_aimage_generation)

    with pytest.raises(LLMError):
        await images_mod.generate_image("a prompt")

    assert provider_health.status_for(provider_health.IMAGES) == (
        CapabilityReason.PROVIDER_QUOTA,
    )
