from src.personalization.modality import resolve_declared_modality
from src.personalization.preferences import (
    InteractionPreference,
    ModalityPreference,
    normalize_learning_preferences,
    preference_bucket,
)


def test_v1_values_normalize_to_canonical_v2_without_losing_interaction() -> None:
    textual = normalize_learning_preferences(
        {"version": 1, "presentation": "textual", "detail": "detailed"}
    )
    interactive = normalize_learning_preferences(
        {"version": 1, "presentation": "interactive"}
    )

    assert textual.modality is ModalityPreference.TEXT
    assert textual.to_dict()["version"] == 2
    assert interactive.modality is ModalityPreference.BALANCED
    assert interactive.interaction is InteractionPreference.INTERACTIVE
    assert preference_bucket(interactive) == (
        "p2:balanced:interactive:standard:when_useful"
    )


def test_audio_degrades_to_text_with_a_closed_trace_when_tts_is_disabled() -> None:
    resolution = resolve_declared_modality(
        {
            "version": 2,
            "modality": "audio",
            "interaction": "interactive",
        },
        tts_available=False,
    )

    assert resolution.requested is ModalityPreference.AUDIO
    assert resolution.effective is ModalityPreference.TEXT
    assert resolution.interaction is InteractionPreference.INTERACTIVE
    assert resolution.trace() == {
        "requested_modality": "audio",
        "effective_modality": "text",
        "interaction": "interactive",
        "fallback_reason": "tts_disabled",
    }


def test_audio_remains_audio_when_tts_is_available() -> None:
    resolution = resolve_declared_modality(
        {"version": 2, "modality": "audio"},
        tts_available=True,
    )

    assert resolution.effective is ModalityPreference.AUDIO
    assert resolution.fallback_reason is None


def test_disabled_audio_uses_the_effective_text_cache_bucket() -> None:
    audio = {"version": 2, "modality": "audio"}
    text = {"version": 2, "modality": "text"}

    assert preference_bucket(audio, tts_available=False) == preference_bucket(text)
    assert preference_bucket(audio, tts_available=True) != preference_bucket(text)
