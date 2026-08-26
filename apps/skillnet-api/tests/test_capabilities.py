"""Capability derivation: the config layer, the runtime layer, and the hint boundary.

No DB, no network. Every case pins ``settings`` (and, for the runtime layer, the in-process
provider-health registry) and asserts the status/reason/hint triple that comes out.
"""

from __future__ import annotations

import pytest

from src.config import settings
from src.schemas.capabilities import Capabilities, CapabilityReason, CapabilityStatus
from src.services import capabilities as cap
from src.services import provider_health


@pytest.fixture(autouse=True)
def _clean_health():
    """The registry is process-global; no test may inherit another's failures."""
    provider_health.reset()
    yield
    provider_health.reset()


@pytest.fixture
def _settings(monkeypatch: pytest.MonkeyPatch):
    """Start from an all-keys-present deployment; tests knock keys out as needed."""
    monkeypatch.setattr(settings, "LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-real")
    monkeypatch.setattr(settings, "TTS_PROVIDER", "azure")
    monkeypatch.setattr(settings, "TTS_API_KEY", "tts-real")
    monkeypatch.setattr(settings, "IMAGE_API_KEY", "")
    monkeypatch.setattr(
        settings, "IMAGE_MODEL", "openrouter/google/gemini-2.5-flash-image"
    )
    monkeypatch.setattr(settings, "IMAGE_FALLBACK_MODEL", "gpt-image-1")
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "or-real")
    return settings


def _no_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setattr(settings, "LLM_API_KEY", "")
    monkeypatch.setattr(settings, "TTS_PROVIDER", "disabled")
    monkeypatch.setattr(settings, "TTS_API_KEY", "")
    monkeypatch.setattr(settings, "IMAGE_API_KEY", "")
    monkeypatch.setattr(
        settings, "IMAGE_MODEL", "openrouter/google/gemini-2.5-flash-image"
    )
    monkeypatch.setattr(settings, "IMAGE_FALLBACK_MODEL", "gpt-image-1")
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")


# --------------------------------------------------------------------------------------
# The config layer
# --------------------------------------------------------------------------------------
def test_all_keys_present_everything_ready(_settings) -> None:
    caps = cap.derive_capabilities()

    for name in ("ai", "generation", "tutor", "tts", "images"):
        capability = getattr(caps, name)
        assert capability.status is CapabilityStatus.READY, name
        assert capability.reason is None, name


def test_no_keys_at_all_blocks_the_ai_family_and_images(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _no_keys(monkeypatch)

    caps = cap.derive_capabilities()

    for name in ("ai", "generation", "tutor", "images"):
        capability = getattr(caps, name)
        assert capability.status is CapabilityStatus.BLOCKED, name
        assert capability.reason is CapabilityReason.MISSING_API_KEY, name


def test_no_keys_leaves_voice_degraded_not_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The podcast fallback chain ends in the keyless offline eSpeak voice, so voice with
    no provider is worse, not absent — and must not switch the podcast off."""
    _no_keys(monkeypatch)

    tts = cap.derive_capabilities().tts

    assert tts.status is CapabilityStatus.DEGRADED
    assert tts.reason is CapabilityReason.NOT_CONFIGURED


def test_llm_only_leaves_images_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_keys(monkeypatch)
    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-real")
    monkeypatch.setattr(settings, "IMAGE_FALLBACK_MODEL", "")

    caps = cap.derive_capabilities()

    assert caps.ai.status is CapabilityStatus.READY
    assert caps.images.status is CapabilityStatus.BLOCKED
    assert caps.images.reason is CapabilityReason.MISSING_API_KEY


def test_llm_plus_images_makes_both_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_keys(monkeypatch)
    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-real")
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "or-real")

    caps = cap.derive_capabilities()

    assert caps.ai.status is CapabilityStatus.READY
    assert caps.images.status is CapabilityStatus.READY


def test_fixture_model_makes_ai_ready_without_a_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _no_keys(monkeypatch)
    monkeypatch.setattr(settings, "LLM_MODEL", "fixture/local")

    caps = cap.derive_capabilities()

    assert caps.ai.status is CapabilityStatus.READY
    assert caps.generation.status is CapabilityStatus.READY
    assert caps.tutor.status is CapabilityStatus.READY


def test_offline_tts_provider_is_ready_without_a_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """eSpeak NG runs locally and takes no credentials."""
    _no_keys(monkeypatch)
    monkeypatch.setattr(settings, "TTS_PROVIDER", "offline")

    tts = cap.derive_capabilities().tts

    assert tts.status is CapabilityStatus.READY
    assert tts.reason is None


def test_cloud_tts_provider_without_a_key_is_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _no_keys(monkeypatch)
    monkeypatch.setattr(settings, "TTS_PROVIDER", "azure")

    tts = cap.derive_capabilities().tts

    assert tts.status is CapabilityStatus.DEGRADED
    assert tts.reason is CapabilityReason.MISSING_API_KEY


def test_image_api_key_overrides_the_per_model_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The image account need not be the text account."""
    _no_keys(monkeypatch)
    monkeypatch.setattr(settings, "IMAGE_API_KEY", "img-real")

    assert cap.derive_capabilities().images.status is CapabilityStatus.READY


# --------------------------------------------------------------------------------------
# The runtime layer — it may only make a capability worse
# --------------------------------------------------------------------------------------
def test_provider_quota_blocks_a_configured_capability(_settings) -> None:
    provider_health.record_failure(provider_health.IMAGES, "quota")

    images = cap.derive_capabilities().images

    assert images.status is CapabilityStatus.BLOCKED
    assert images.reason is CapabilityReason.PROVIDER_QUOTA


def test_provider_down_blocks_the_llm_family(_settings) -> None:
    provider_health.record_failure(provider_health.LLM, "down")

    caps = cap.derive_capabilities()

    for name in ("ai", "generation", "tutor"):
        capability = getattr(caps, name)
        assert capability.status is CapabilityStatus.BLOCKED, name
        assert capability.reason is CapabilityReason.PROVIDER_DOWN, name


def test_a_failing_voice_provider_degrades_rather_than_blocks(_settings) -> None:
    """There is always the offline voice underneath, so voice never reaches BLOCKED."""
    provider_health.record_failure(provider_health.TTS, "down")

    tts = cap.derive_capabilities().tts

    assert tts.status is CapabilityStatus.DEGRADED
    assert tts.reason is CapabilityReason.PROVIDER_DOWN


def test_provider_health_cannot_make_a_missing_key_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runtime layer only ever worsens: a healthy registry conjures no key."""
    _no_keys(monkeypatch)

    caps = cap.derive_capabilities()

    assert caps.images.status is CapabilityStatus.BLOCKED
    assert caps.images.reason is CapabilityReason.MISSING_API_KEY


# --------------------------------------------------------------------------------------
# The hint boundary
# --------------------------------------------------------------------------------------
def test_hints_are_absent_unless_asked_for(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_keys(monkeypatch)

    caps = cap.derive_capabilities()

    for name in Capabilities.model_fields:
        assert getattr(caps, name).hint is None, name


def test_hints_are_present_and_actionable_when_asked_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _no_keys(monkeypatch)

    caps = cap.derive_capabilities(include_hints=True)

    assert "IMAGE_API_KEY" in caps.images.hint
    assert "LLM_API_KEY" in caps.ai.hint
    # generation/tutor are the same LLM under two names; they share its hint.
    assert caps.generation.hint == caps.ai.hint
    assert caps.tutor.hint == caps.ai.hint


def test_a_ready_capability_carries_no_hint(_settings) -> None:
    caps = cap.derive_capabilities(include_hints=True)

    assert caps.ai.hint is None
    assert caps.images.hint is None
