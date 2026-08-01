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
from src.deps.auth import CurrentUser
from src.schemas.tts import TTSRequest, TTSVoicesResponse
from src.services.tts_service import TTSService, get_tts_provider

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
    """
    service = _get_service()
    audio = await service.synthesize(
        text=body.text,
        voice=body.voice if body.voice != "default" else None,
        language=body.language,
    )
    return Response(content=audio, media_type="audio/mpeg")


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
