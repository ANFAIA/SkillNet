"""TTS request and response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from src.core.language import DEFAULT_LANGUAGE, Language, normalize_language


class TTSRequest(BaseModel):
    """Body for ``POST /api/v1/tts/synthesize``."""

    text: str = Field(..., min_length=1, max_length=5000)
    voice: str = "default"
    #: Typed and normalized rather than a free string, so a browser locale (``en-US``,
    #: ``es_ES``) reaches the provider as a language it recognises. Still defaults to the
    #: platform default and not to ``None``: unlike a generation, the provider needs *a*
    #: language to pick a voice, and this body carries text the caller already has — there
    #: is no course to resolve it from here. Whoever renders the mascot's line knows which
    #: language it is in and should say so.
    language: Language = DEFAULT_LANGUAGE

    @field_validator("language", mode="before")
    @classmethod
    def _normalize_language(cls, value: object) -> Language:
        return normalize_language(None if value is None else str(value)) or DEFAULT_LANGUAGE


class TTSVoice(BaseModel):
    id: str
    name: str


class TTSVoicesResponse(BaseModel):
    provider: str
    voices: list[TTSVoice]
