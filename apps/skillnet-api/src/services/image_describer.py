"""Describe images extracted from PDFs using a vision-capable LLM.

Best-effort: if the configured model does not support vision, or the call
fails for any reason, the image is silently skipped. Document ingestion must
never fail because of an image description failure — the text content is
always sufficient for a usable course.

Requires ``VISION_MODEL`` in the environment (or org settings). When absent,
image description is disabled entirely — no LLM call is attempted.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

import litellm

from src.config import settings
from src.core.logging import get_logger
from src.llm.client import LLMConfig, resolve_llm_config

logger = get_logger(__name__)

#: Images smaller than this are likely decorative (icons, bullets, borders).
MIN_IMAGE_BYTES = 5_000

_DESCRIBE_PROMPT = (
    "Describe this image concisely in 2-3 sentences, in Spanish. "
    "Focus on what it shows (diagrams, charts, photos, processes) and any "
    "text or data visible. Do not add commentary about the image quality."
)


@dataclass
class ImageDescription:
    page: int
    description: str


def resolve_vision_config(
    org_settings: dict | None = None,
) -> LLMConfig | None:
    """Return vision LLM config, or ``None`` if no vision model is configured.

    Precedence: org_settings['vision_model'] > VISION_MODEL env var.
    Falls back to the main LLM_MODEL only if VISION_MODEL is explicitly set
    to the same value — we never assume the default LLM supports vision.
    """
    org_settings = org_settings or {}

    model = org_settings.get("vision_model") or getattr(settings, "VISION_MODEL", None)
    if not model:
        return None

    # Reuse the main LLM connection settings (api_key, base_url) unless
    # the org overrides them specifically for vision.
    base = resolve_llm_config(org_settings)
    return LLMConfig(
        model=str(model),
        api_base=org_settings.get("vision_base_url") or base.api_base,
        api_key=org_settings.get("vision_api_key") or base.api_key,
    )


def _encode_image(image_bytes: bytes) -> str:
    """Build a data URL from raw image bytes."""
    if image_bytes[:4] == b"\x89PNG":
        mime = "image/png"
    elif image_bytes[:2] == b"\xff\xd8":
        mime = "image/jpeg"
    else:
        mime = "image/png"
    return f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"


async def describe_image(
    image_bytes: bytes,
    config: LLMConfig,
) -> str | None:
    """Send one image to the vision model, return its description or None."""
    try:
        response = await litellm.acompletion(
            model=config.model,
            api_base=config.api_base,
            api_key=config.api_key,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _DESCRIBE_PROMPT},
                        {"type": "image_url", "image_url": {"url": _encode_image(image_bytes)}},
                    ],
                }
            ],
            temperature=0.1,
            max_tokens=200,
        )
        choices = getattr(response, "choices", None) or ()
        if not choices:
            return None
        content = getattr(choices[0].message, "content", None)
        return content.strip() if content else None
    except Exception as exc:  # noqa: BLE001 — best effort
        logger.warning("Vision description failed (%s): %s", config.model, exc)
        return None
