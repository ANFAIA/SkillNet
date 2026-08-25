"""Image generation for media artifacts (spine item #4).

One function, ``generate_image``, going through litellm exactly like every other model
call in the app (``src/llm/client.py`` — no provider SDK imported directly). The default
model is NotebookLM's actual engine family, Gemini 2.5 Flash Image ("Nano Banana"),
reached through OpenRouter; ``gpt-image-1`` on the existing OpenAI key is the fallback,
selectable per call or by config.

The provider returns the image as base64 in ``resp.data[0].b64_json``; some models (older
DALL-E, some OpenRouter routes) return a URL instead, so both are handled and decoded to
raw PNG bytes the caller can hand straight to the asset store.
"""

from __future__ import annotations

import base64

import litellm

from src.config import settings
from src.core.exceptions import LLMError
from src.core.logging import get_logger

logger = get_logger(__name__)


def _api_key_for(model: str) -> str | None:
    """The key litellm needs for this model's provider.

    OpenRouter models authenticate with ``OPENROUTER_API_KEY``; ``gpt-image-1`` and other
    OpenAI models use the same key the rest of the app uses (``LLM_API_KEY``). Passed
    explicitly rather than relying on ``os.environ`` so the config file is the single
    source of truth.
    """
    if model.startswith("openrouter/"):
        return settings.OPENROUTER_API_KEY or None
    return settings.LLM_API_KEY or None


async def _decode_image(resp: object) -> bytes:
    """Pull raw bytes out of a litellm image response (b64 first, URL fallback)."""
    data = getattr(resp, "data", None) or []
    if not data:
        raise LLMError("Image provider returned no data")
    item = data[0]
    b64 = getattr(item, "b64_json", None) or (
        item.get("b64_json") if isinstance(item, dict) else None
    )
    if b64:
        return base64.b64decode(b64)
    url = getattr(item, "url", None) or (
        item.get("url") if isinstance(item, dict) else None
    )
    if url:
        import httpx

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content
    raise LLMError("Image response carried neither b64_json nor url")


async def generate_image(
    prompt: str,
    *,
    size: str = "1024x1024",
    model: str | None = None,
    fallback: bool = True,
) -> bytes:
    """Generate one image and return its raw (PNG) bytes.

    ``model`` overrides the configured default (``settings.IMAGE_MODEL``). When the primary
    model fails and ``fallback`` is set, ``settings.IMAGE_FALLBACK_MODEL`` (gpt-image-1 on
    the OpenAI key) is tried once — the roadmap's declared stopgap. The final failure is
    normalized to :class:`LLMError`, same as the text client.
    """
    primary = model or settings.IMAGE_MODEL
    attempts = [primary]
    if fallback and settings.IMAGE_FALLBACK_MODEL not in attempts:
        attempts.append(settings.IMAGE_FALLBACK_MODEL)

    last_exc: Exception | None = None
    for candidate in attempts:
        api_key = _api_key_for(candidate)
        if not api_key:
            # Mirrors the TTS path (DialogueUnsupported before any network call): skip a
            # candidate with no configured key instead of spending a real round-trip on a
            # request that is guaranteed to fail auth, so a deployment with no image key
            # degrades to spec-only immediately rather than after two wasted attempts.
            last_exc = LLMError(f"no API key configured for {candidate}")
            logger.info("Skipping image model %s: no API key configured", candidate)
            continue
        try:
            resp = await litellm.aimage_generation(
                model=candidate,
                prompt=prompt,
                size=size,
                n=1,
                api_key=api_key,
            )
            return await _decode_image(resp)
        except Exception as exc:  # noqa: BLE001 - normalized and possibly retried below
            last_exc = exc
            logger.warning("Image generation with %s failed: %s", candidate, exc)

    raise LLMError(
        f"Image generation failed for {attempts}: {type(last_exc).__name__}: {last_exc}"
    )


__all__ = ["generate_image"]
