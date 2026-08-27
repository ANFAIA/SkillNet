"""What this deployment can actually do, and — when the reader is allowed to know — why not.

A capability used to be a bare boolean, which could say "no" but never "why", so the UI
could only grey a button out with no explanation and the API could only accept a job that
was doomed. Each capability is now a :class:`Capability`: a status, an optional machine
readable reason, and an optional admin-only hint.

Two layers produce it (see ``services.capabilities.derive_capabilities``):

* the **config layer** — a pure read of ``settings``: no network, no filesystem, cannot
  fail. That purity is what lets the result be served on the public, pre-authentication
  ``GET /setup/status``.
* the **runtime layer** — ``services.provider_health``, a TTL registry of recent provider
  failures. It may only make a capability *worse*, never better.

**``hint`` is admin-only.** It names environment variables, and ``GET /setup/status`` is
answered before anyone has authenticated: telling an anonymous caller which key a
deployment is missing is configuration disclosure (docs/design/security.md). The public
payload therefore carries ``status`` and ``reason`` and nothing else, which is enough for
the UI to disable a control and say "unavailable in this installation".
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class CapabilityStatus(StrEnum):
    """How usable a capability is right now."""

    #: Fully usable.
    READY = "ready"
    #: Usable, but on a lesser path (e.g. voice falls back to the offline eSpeak engine).
    #: Callers are *not* refused: a degraded capability still produces a real result.
    DEGRADED = "degraded"
    #: Not usable at all. Anything requiring it is refused up front rather than accepted
    #: and failed thirty seconds later.
    BLOCKED = "blocked"


class CapabilityReason(StrEnum):
    """Why a capability is not ``READY``. Machine-readable; the UI writes the prose."""

    #: No usable key for this capability's provider.
    MISSING_API_KEY = "missing_api_key"
    #: The provider is explicitly switched off in configuration.
    NOT_CONFIGURED = "not_configured"
    #: The provider recently answered 429/402 — out of quota or out of credit.
    PROVIDER_QUOTA = "provider_quota"
    #: The provider recently failed hard or timed out.
    PROVIDER_DOWN = "provider_down"


class Capability(BaseModel):
    """One capability's state.

    ``hint`` is short, actionable English aimed at whoever owns the ``.env``. It is
    ``None`` on every public payload — see this module's docstring.
    """

    status: CapabilityStatus
    reason: CapabilityReason | None = None
    hint: str | None = None

    @property
    def is_ready(self) -> bool:
        return self.status is CapabilityStatus.READY

    @property
    def is_blocked(self) -> bool:
        return self.status is CapabilityStatus.BLOCKED


class Capabilities(BaseModel):
    """The capability set of this deployment. Same keys it has always had.

    Computed by ``services.capabilities.derive_capabilities``; the single source of truth
    for capability-driven onboarding and degraded-mode UX (docs/design/onboarding.md §2.1).
    """

    #: A usable LLM exists (API key, or a fixture model that needs none). Nothing AI works
    #: without it.
    ai: Capability
    #: Generate courses/lessons (same LLM as ``ai``).
    generation: Capability
    #: Chat tutor (same LLM as ``ai``).
    tutor: Capability
    #: Voice (mascot / podcast / video narration). Degrades rather than blocks: the podcast
    #: chain ends in an offline eSpeak voice that needs no key.
    tts: Capability
    #: Infographic posters and slide illustrations. Blocks rather than degrades — a
    #: deployment with no image key cannot make them at all.
    images: Capability
    #: "Sign in with Google" is configured, so the login screen may offer it. Not an AI
    #: capability, but it rides the same config-derived channel the login screen already
    #: reads before anyone is authenticated.
    google_login: Capability


#: The capability keys, in the order :class:`Capabilities` declares them. The requirements
#: registry validates against this, so a typo there is a startup error and not a silently
#: ignored requirement.
CAPABILITY_NAMES: tuple[str, ...] = tuple(Capabilities.model_fields)


class CapabilitiesReport(BaseModel):
    """The whole capability payload: the capabilities plus what each media kind needs.

    ``media_requirements`` maps a ``MediaKind`` value to the capability names that kind
    requires, so the frontend disables a Studio button by *reading* the table instead of
    hardcoding a second copy of it that drifts. Both keys travel on the public
    ``GET /setup/status`` too, so one reader serves both endpoints.
    """

    capabilities: Capabilities
    media_requirements: dict[str, list[str]]


__all__ = [
    "CAPABILITY_NAMES",
    "Capabilities",
    "CapabilitiesReport",
    "Capability",
    "CapabilityReason",
    "CapabilityStatus",
]
