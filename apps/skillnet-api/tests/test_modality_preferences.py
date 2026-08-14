from src.personalization.modality import resolve_declared_modality
from src.personalization.preferences import (
    CompanionModality,
    InteractionPreference,
    ModalityPreference,
    normalize_learning_preferences,
    preference_bucket,
)


def test_v1_values_normalize_to_canonical_v3_without_losing_interaction() -> None:
    textual = normalize_learning_preferences(
        {"version": 1, "presentation": "textual", "detail": "detailed"}
    )
    interactive = normalize_learning_preferences(
        {"version": 1, "presentation": "interactive"}
    )

    assert textual.modality is ModalityPreference.TEXT
    assert textual.to_dict()["version"] == 3
    assert interactive.modality is ModalityPreference.BALANCED
    assert interactive.interaction is InteractionPreference.INTERACTIVE
    assert preference_bucket(interactive) == (
        "p3:balanced:interactive:standard:when_useful"
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


def test_audio_never_partitions_the_web_render_cache() -> None:
    audio = {"version": 2, "modality": "audio"}
    balanced = {"version": 2, "modality": "balanced"}

    assert preference_bucket(audio, tts_available=False) == preference_bucket(balanced)
    assert preference_bucket(audio, tts_available=True) == preference_bucket(balanced)


def test_v3_keeps_audio_and_video_as_additive_companions() -> None:
    preferences = normalize_learning_preferences(
        {"version": 3, "web_presentation": "visual", "modalities": ["video", "audio"]}
    )

    assert preferences.modalities == (
        CompanionModality.AUDIO,
        CompanionModality.VIDEO,
    )
    assert preferences.to_dict()["modalities"] == ["audio", "video"]
