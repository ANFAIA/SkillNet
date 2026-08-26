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
from src.services import provider_health

logger = get_logger(__name__)


def api_key_for(model: str) -> str | None:
    """The key litellm needs for this model's provider, or ``None`` if none is configured.

    Resolution order:

    1. ``IMAGE_API_KEY`` when set — it always wins, whatever the model is.
    2. Otherwise the historic rule: ``openrouter/*`` authenticates with
       ``OPENROUTER_API_KEY``, anything else reuses ``LLM_API_KEY``.

    ``IMAGE_API_KEY`` exists because rule 2 quietly assumes the text and the image provider
    are the same account. They often are not: a deployment on Groq for text and OpenAI for
    ``gpt-image-1`` sends the Groq key to OpenAI, which fails auth and looks *exactly* like
    a missing key — the same symptom, a different cause, and no way to tell them apart from
    the outside. One explicit setting removes the guess.

    This is the one function that answers "can this deployment generate images", and
    ``services.capabilities`` imports it rather than mirroring it. The mirror it replaces
    had already drifted: it consulted only ``IMAGE_MODEL`` and so reported ``images=False``
    for a deployment whose ``gpt-image-1`` fallback would have worked.

    Passed explicitly to litellm rather than relying on ``os.environ`` so the config file
    stays the single source of truth.
    """
    if settings.IMAGE_API_KEY:
        return settings.IMAGE_API_KEY
    if model.startswith("openrouter/"):
        return settings.OPENROUTER_API_KEY or None
    return settings.LLM_API_KEY or None


def model_candidates(model: str | None = None, *, fallback: bool = True) -> list[str]:
    """The models :func:`generate_image` will try, in order.

    Shared with the capability derivation so "what will be attempted" and "is any of it
    usable" can never answer about different lists.
    """
    # An empty setting is "no model", not a model named "": without this guard the blank
    # fallback resolves to the text key and reports images as available.
    candidates = [name for name in (model or settings.IMAGE_MODEL,) if name]
    if fallback and settings.IMAGE_FALLBACK_MODEL:
        if settings.IMAGE_FALLBACK_MODEL not in candidates:
            candidates.append(settings.IMAGE_FALLBACK_MODEL)
    return candidates


def images_are_available() -> bool:
    """True when at least one configured image model has a key to authenticate with."""
    return any(api_key_for(candidate) for candidate in model_candidates())


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
    attempts = model_candidates(model, fallback=fallback)

    last_exc: Exception | None = None
    for candidate in attempts:
        api_key = api_key_for(candidate)
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
            # A key that is present but out of quota looks perfect to the config read in
            # `services.capabilities`; this is the only place that knows better.
            provider_health.record_failure(
                provider_health.IMAGES, provider_health.failure_kind(exc)
            )
            logger.warning("Image generation with %s failed: %s", candidate, exc)

    raise LLMError(
        f"Image generation failed for {attempts}: {type(last_exc).__name__}: {last_exc}"
    )


__all__ = ["api_key_for", "generate_image", "images_are_available", "model_candidates"]
