"""TTS routes: synthesize speech and list available voices.

Auth: both endpoints require an active session (``CurrentUser``). The TTS
provider is configured through env vars (``TTS_PROVIDER``, ``TTS_API_KEY``) and
follows the same philosophy as the LLM provider — infrastructure, not a web form.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from src.config import settings
from src.core.exceptions import AppError
from src.core.logging import get_logger
from src.deps.auth import CurrentUser
from src.schemas.tts import TTSRequest, TTSVoicesResponse
from src.services.tts_service import TTSService, get_tts_provider

logger = get_logger(__name__)

# Map frontend voice styles to provider-specific voice IDs.
_VOICE_STYLE_MAP: dict[str, dict[str, str]] = {
    "openai": {"neutral": "alloy", "warm": "nova", "formal": "onyx"},
    "elevenlabs": {
        "neutral": "21m00Tcm4TlvDq8ikWAM",  # Rachel
        "warm": "EXAVITQu4vr4xnSDxMaL",     # Sarah
        "formal": "pNInz6obpgDQGcFmaJgB",    # Adam
    },
    "google": {
        "neutral": "es-ES-Wavenet-B",
        "warm": "es-ES-Wavenet-C",
        "formal": "es-ES-Wavenet-D",
    },
    "azure": {
        "neutral": "es-ES-ElviraNeural",
        "warm": "es-ES-AlvaroNeural",
        "formal": "es-ES-ElviraNeural",
    },
}


def _resolve_voice(voice: str) -> str | None:
    """Turn a style name into a provider voice ID, or pass through."""
    if voice == "default":
        return None
    provider_map = _VOICE_STYLE_MAP.get(settings.TTS_PROVIDER, {})
    return provider_map.get(voice, voice)

router = APIRouter(prefix="/tts", tags=["TTS"])


def _get_service() -> TTSService:
    """Build the service from env-configured provider. Raises a clear 503 if disabled."""
    if settings.TTS_PROVIDER == "disabled":
        raise AppError(
            message="TTS is disabled in this deployment. Set TTS_PROVIDER to enable it.",
            code="TTS_DISABLED",
            status_code=503,
        )
    return TTSService()


@router.post("/synthesize")
async def synthesize(body: TTSRequest, user: CurrentUser) -> Response:
    """Synthesize text to speech. Returns audio/mpeg bytes.

    The audio is cached on disk: identical requests are served from cache without
    hitting the provider again.

    Degrades gracefully instead of hard-failing: if the configured provider errors
    (e.g. ElevenLabs quota_exceeded), it falls back to the offline eSpeak voice so the
    mascot still has *a* voice — the same safety net the podcast path uses. Only when even
    the offline provider fails does it return a clean ``204 No Content`` (no audio), which
    the mascot frontend already tolerates by staying silent. It never returns a 500.
    """
    service = _get_service()
    try:
        audio = await service.synthesize(
            text=body.text,
            voice=_resolve_voice(body.voice),
            language=body.language,
        )
        return Response(content=audio, media_type="audio/mpeg")
    except Exception as exc:  # noqa: BLE001 - any provider failure degrades, never 500s
        logger.warning(
            "TTS provider %s failed, falling back to offline: %s",
            settings.TTS_PROVIDER,
            exc,
        )

    # Fallback: offline eSpeak NG — no key, no quota. Pass its own default voice rather
    # than the primary provider's voice id (an ElevenLabs id is not a valid espeak spec).
    if settings.TTS_PROVIDER != "offline":
        try:
            offline = TTSService(provider=get_tts_provider("offline", ""))
            audio = await offline.synthesize(text=body.text, voice=None, language=body.language)
            return Response(content=audio, media_type="audio/mpeg")
        except Exception as exc:  # noqa: BLE001 - offline failed too; degrade to "no voice"
            logger.warning("Offline TTS fallback failed, returning 204: %s", exc)

    # Even offline failed (or is the primary): return a clean "no voice" the UI tolerates.
    return Response(status_code=204)


@router.get("/voices", response_model=TTSVoicesResponse)
async def list_voices(user: CurrentUser) -> TTSVoicesResponse:
    """List available voices for the configured TTS provider."""
    if settings.TTS_PROVIDER == "disabled":
        raise AppError(
            message="TTS is disabled in this deployment.",
            code="TTS_DISABLED",
            status_code=503,
        )
    provider = get_tts_provider(settings.TTS_PROVIDER, settings.TTS_API_KEY)
    return TTSVoicesResponse(
        provider=settings.TTS_PROVIDER,
        voices=provider.available_voices(),
    )
