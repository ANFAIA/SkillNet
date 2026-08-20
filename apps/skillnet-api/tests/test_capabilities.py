"""Capabilities derivation — a pure config read (docs/design/onboarding.md §2.1).

No DB, no network: every case just pins settings and asserts which booleans light up.
"""

from __future__ import annotations

import pytest

from src.services import capabilities as cap


@pytest.fixture
def _settings(monkeypatch: pytest.MonkeyPatch):
    """Start from an all-keys-present deployment; tests knock keys out as needed."""
    monkeypatch.setattr(cap.settings, "LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setattr(cap.settings, "LLM_API_KEY", "sk-real")
    monkeypatch.setattr(cap.settings, "TTS_PROVIDER", "azure")
    monkeypatch.setattr(cap.settings, "TTS_API_KEY", "tts-real")
    monkeypatch.setattr(cap.settings, "IMAGE_MODEL", "openrouter/google/gemini-2.5-flash-image")
    monkeypatch.setattr(cap.settings, "OPENROUTER_API_KEY", "or-real")
    return cap.settings


def test_all_keys_present_all_true(_settings) -> None:
    caps = cap.derive_capabilities()
    assert (caps.ai, caps.generation, caps.tutor, caps.tts, caps.images) == (
        True,
        True,
        True,
        True,
        True,
    )


def test_no_keys_at_all_only_ai_family_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cap.settings, "LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setattr(cap.settings, "LLM_API_KEY", "")
    monkeypatch.setattr(cap.settings, "TTS_PROVIDER", "disabled")
    monkeypatch.setattr(cap.settings, "TTS_API_KEY", "")
    monkeypatch.setattr(cap.settings, "IMAGE_MODEL", "openrouter/google/gemini-2.5-flash-image")
    monkeypatch.setattr(cap.settings, "OPENROUTER_API_KEY", "")
    caps = cap.derive_capabilities()
    assert not any((caps.ai, caps.generation, caps.tutor, caps.tts, caps.images))


def test_fixture_model_makes_ai_available_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cap.settings, "LLM_MODEL", "fixture/local")
    monkeypatch.setattr(cap.settings, "LLM_API_KEY", "")
    caps = cap.derive_capabilities()
    assert caps.ai and caps.generation and caps.tutor


def test_tts_needs_both_provider_and_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cap.settings, "LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setattr(cap.settings, "LLM_API_KEY", "sk-real")
    # Provider enabled but no key -> not usable.
    monkeypatch.setattr(cap.settings, "TTS_PROVIDER", "azure")
    monkeypatch.setattr(cap.settings, "TTS_API_KEY", "")
    assert cap.derive_capabilities().tts is False
    # Key present but provider disabled -> not usable.
    monkeypatch.setattr(cap.settings, "TTS_PROVIDER", "disabled")
    monkeypatch.setattr(cap.settings, "TTS_API_KEY", "tts-real")
    assert cap.derive_capabilities().tts is False


def test_images_openrouter_vs_openai_key_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cap.settings, "LLM_API_KEY", "sk-real")
    # OpenRouter image model authenticates with OPENROUTER_API_KEY, not LLM_API_KEY.
    monkeypatch.setattr(cap.settings, "IMAGE_MODEL", "openrouter/google/gemini-2.5-flash-image")
    monkeypatch.setattr(cap.settings, "OPENROUTER_API_KEY", "")
    assert cap.derive_capabilities().images is False
    # An OpenAI image model reuses LLM_API_KEY.
    monkeypatch.setattr(cap.settings, "IMAGE_MODEL", "gpt-image-1")
    assert cap.derive_capabilities().images is True
