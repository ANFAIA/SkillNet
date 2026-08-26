"""Which AI capabilities this deployment has, derived from config alone.

The single source of truth behind capability-driven onboarding, degraded-mode UX
and smart defaults (see docs/design/onboarding.md §2.1). It is a *pure* read of
``settings`` — presence of keys/models, never a live call to a provider — so it is
cheap enough to serve on every ``GET /setup/status`` and can never itself fail.
"""

from __future__ import annotations

from src.config import settings
from src.llm.fixtures import FIXTURE_PREFIX
from src.personalization.modality import tts_is_available
from src.schemas.setup import Capabilities
from src.services.google_oauth import is_enabled as google_oauth_is_enabled


def _llm_is_available() -> bool:
    """True when the app has a usable LLM: an API key, or a fixture model that
    replays recorded responses with no key and no network (``fixture/local``)."""
    if settings.LLM_MODEL.startswith(FIXTURE_PREFIX):
        return True
    return bool(settings.LLM_API_KEY)


def _images_are_available() -> bool:
    """Mirror of ``services.media.images._api_key_for``: OpenRouter image models
    authenticate with ``OPENROUTER_API_KEY``; OpenAI ones (gpt-image-1) reuse
    ``LLM_API_KEY``."""
    if settings.IMAGE_MODEL.startswith("openrouter/"):
        return bool(settings.OPENROUTER_API_KEY)
    return bool(settings.LLM_API_KEY)


def derive_capabilities() -> Capabilities:
    ai = _llm_is_available()
    return Capabilities(
        ai=ai,
        # Generation and the tutor are the same LLM; without it neither runs.
        generation=ai,
        tutor=ai,
        tts=tts_is_available(settings.TTS_PROVIDER) and bool(settings.TTS_API_KEY),
        images=_images_are_available(),
        google_login=google_oauth_is_enabled(),
    )
