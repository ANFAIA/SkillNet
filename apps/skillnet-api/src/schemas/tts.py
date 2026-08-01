"""TTS request and response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TTSRequest(BaseModel):
    """Body for ``POST /api/v1/tts/synthesize``."""

    text: str = Field(..., min_length=1, max_length=5000)
    voice: str = "default"
    language: str = "es"


class TTSVoice(BaseModel):
    id: str
    name: str


class TTSVoicesResponse(BaseModel):
    provider: str
    voices: list[TTSVoice]
