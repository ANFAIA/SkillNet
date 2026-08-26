"""Which AI capabilities this deployment has, and why not when it does not.

Two layers, composed by :func:`derive_capabilities`:

* The **config layer** is a pure read of ``settings`` — presence of keys, models and
  providers, never a live call. It cannot fail and costs nothing, which is exactly what
  lets its result be served on the public, pre-authentication ``GET /setup/status``.
* The **runtime layer** is :mod:`src.services.provider_health`, a TTL registry of recent
  provider failures. It may only make a capability *worse*: a key that is present but out
  of quota is invisible to a config read, while a provider that recently 429'd says
  nothing about whether a key exists. Never the other way round — a healthy-looking
  registry cannot conjure a key that is not configured.

``hint`` is admin-only and is filled only when ``include_hints=True``. It names environment
variables, and the public endpoint answers before anyone has authenticated. There is one
derivation, not two, so the public and the admin payloads can never disagree about what is
available — they differ in exactly one field.
"""

from __future__ import annotations

from src.config import settings
from src.llm.fixtures import FIXTURE_PREFIX
from src.personalization.modality import tts_is_available
from src.schemas.capabilities import (
    Capabilities,
    Capability,
    CapabilityReason,
    CapabilityStatus,
)
from src.services import provider_health
from src.services.google_oauth import is_enabled as google_oauth_is_enabled
from src.services.media.images import images_are_available

#: Short, actionable, English, aimed at whoever owns the deployment's ``.env``.
_HINTS: dict[CapabilityReason, dict[str, str]] = {
    CapabilityReason.MISSING_API_KEY: {
        "ai": "Set LLM_API_KEY in the deployment .env (or LLM_MODEL=fixture/local to run "
        "with recorded responses and no key).",
        "images": "Set IMAGE_API_KEY (or OPENROUTER_API_KEY) in the deployment .env.",
        "tts": "Set TTS_API_KEY in the deployment .env, or TTS_PROVIDER=offline to use the "
        "keyless eSpeak voice.",
    },
    CapabilityReason.NOT_CONFIGURED: {
        "tts": "Set TTS_PROVIDER (offline needs no key) and TTS_API_KEY in the deployment "
        ".env.",
        "google_login": "Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET and "
        "GOOGLE_REDIRECT_URI in the deployment .env.",
    },
    CapabilityReason.PROVIDER_QUOTA: {
        "ai": "The LLM provider is refusing calls for quota or credit. Check the account's "
        "plan; this clears itself once calls succeed again.",
        "images": "The image provider is refusing calls for quota or credit. Check the "
        "account's plan; this clears itself once calls succeed again.",
        "tts": "The voice provider is refusing calls for quota or credit. Check the "
        "account's plan; this clears itself once calls succeed again.",
    },
    CapabilityReason.PROVIDER_DOWN: {
        "ai": "Recent LLM calls failed or timed out. Check LLM_BASE_URL and the provider's "
        "status; this clears itself once calls succeed again.",
        "images": "Recent image calls failed or timed out. Check IMAGE_MODEL and the "
        "provider's status; this clears itself once calls succeed again.",
        "tts": "Recent voice calls failed or timed out. Check TTS_PROVIDER and the "
        "provider's status; this clears itself once calls succeed again.",
    },
}

#: The provider slot each capability draws on, for the runtime layer. ``google_login`` has
#: none: it is a redirect this app never calls a provider for.
_PROVIDER_OF: dict[str, str] = {
    "ai": provider_health.LLM,
    "generation": provider_health.LLM,
    "tutor": provider_health.LLM,
    "images": provider_health.IMAGES,
    "tts": provider_health.TTS,
}

#: Capabilities whose worst case is DEGRADED rather than BLOCKED, because a keyless local
#: path underneath them still produces a real result. Only ``tts`` qualifies: every podcast
#: and video-narration fallback chain ends in the offline eSpeak voice
#: (``media/podcast/voices._build_fallback_chain``), which needs no key, no quota and no
#: network. Blocking it would switch off a feature that works today.
_HAS_LOCAL_FALLBACK: frozenset[str] = frozenset({"tts"})


def _llm_is_available() -> bool:
    """True when the app has a usable LLM: an API key, or a fixture model that
    replays recorded responses with no key and no network (``fixture/local``)."""
    if settings.LLM_MODEL.startswith(FIXTURE_PREFIX):
        return True
    return bool(settings.LLM_API_KEY)


def _tts_config_state() -> tuple[CapabilityStatus, CapabilityReason | None]:
    """The configured voice path, read honestly against what the code actually does.

    ``TTS_PROVIDER=offline`` is READY *without* a key: eSpeak NG runs locally and takes no
    credentials. A cloud provider needs its key. With no usable cloud provider the podcast
    and video chains still voice their content through the offline fallback, so this is
    DEGRADED — robotic, not absent — and the media gate lets it through.
    """
    provider = str(settings.TTS_PROVIDER or "").strip().lower()
    if provider == "offline":
        return CapabilityStatus.READY, None
    if not tts_is_available(provider):
        return CapabilityStatus.DEGRADED, CapabilityReason.NOT_CONFIGURED
    if not settings.TTS_API_KEY:
        return CapabilityStatus.DEGRADED, CapabilityReason.MISSING_API_KEY
    return CapabilityStatus.READY, None


def _capability(
    name: str,
    status: CapabilityStatus,
    reason: CapabilityReason | None,
    *,
    include_hints: bool,
) -> Capability:
    """Apply the runtime layer on top of a config verdict, then attach the hint."""
    if status is CapabilityStatus.READY:
        recent = provider_health.status_for(_PROVIDER_OF.get(name, ""))
        if recent:
            reason = recent[0]
            status = (
                CapabilityStatus.DEGRADED
                if name in _HAS_LOCAL_FALLBACK
                else CapabilityStatus.BLOCKED
            )
    hint = None
    if include_hints and reason is not None:
        # `generation` and `tutor` ARE the LLM capability under two names, so they share
        # its hint rather than repeating it in three places that could disagree.
        hints = _HINTS.get(reason, {})
        hint = hints.get(name) or (
            hints.get("ai") if name in ("generation", "tutor") else None
        )
    return Capability(status=status, reason=reason, hint=hint)


def derive_capabilities(*, include_hints: bool = False) -> Capabilities:
    """The deployment's capabilities. ``include_hints`` is for authenticated admins only.

    Never raises and never touches the network: a capability read is on the path of the
    public status endpoint, and an endpoint that says "I could not work out whether I
    work" is of no use to anybody.
    """
    llm_status = (
        (CapabilityStatus.READY, None)
        if _llm_is_available()
        else (CapabilityStatus.BLOCKED, CapabilityReason.MISSING_API_KEY)
    )
    tts_status = _tts_config_state()
    images_status = (
        (CapabilityStatus.READY, None)
        if images_are_available()
        else (CapabilityStatus.BLOCKED, CapabilityReason.MISSING_API_KEY)
    )
    google_status = (
        (CapabilityStatus.READY, None)
        if google_oauth_is_enabled()
        else (CapabilityStatus.BLOCKED, CapabilityReason.NOT_CONFIGURED)
    )

    def build(name: str, verdict: tuple[CapabilityStatus, CapabilityReason | None]):
        return _capability(name, verdict[0], verdict[1], include_hints=include_hints)

    return Capabilities(
        ai=build("ai", llm_status),
        # Generation and the tutor are the same LLM; without it neither runs.
        generation=build("generation", llm_status),
        tutor=build("tutor", llm_status),
        tts=build("tts", tts_status),
        images=build("images", images_status),
        google_login=build("google_login", google_status),
    )


__all__ = ["derive_capabilities"]
