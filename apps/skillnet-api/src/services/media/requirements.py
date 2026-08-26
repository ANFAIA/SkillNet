"""What each media kind needs from the deployment — declared once, read everywhere.

The table below is the ONLY place that says "an infographic needs image generation". The
route reads it to refuse a job it cannot finish, and it travels to the frontend on the
capabilities payload so the Studio buttons are disabled from the same table rather than
from a second copy of it that drifts.

The requirements are the ones the generators actually have, verified in code:

* ``ai`` — every kind with a real generator opens with an LLM content stage that raises
  :class:`~src.core.exceptions.LLMError` without a key (``podcast/script.py``,
  ``slides/spec.py``, ``infographic/spec.py``, ``video/narration.py``).
* ``images`` — the infographic poster, the slide illustrations and the video's per-slide
  illustrations all go through ``media.images.generate_image``.
* ``tts`` — the podcast and the video narration go through the podcast voice chain.

The kinds with no real generator (``mindmap``, ``report``, ``cover_image``) still resolve
to :class:`~src.services.media.jobs.EchoGenerator`, which calls nothing and therefore
requires nothing. They are listed explicitly, with an empty tuple, so that adding a kind
without deciding its requirements fails the completeness test instead of silently
defaulting to "needs nothing".

Note on ``images``: the generators treat a failed image as *best-effort* and fall back to a
spec-only artefact. The owner's decision overrides that at the door — with no image model a
poster is not "degraded", it is unavailable, and the user is told so before they wait.
"""

from __future__ import annotations

from src.core.exceptions import CapabilityBlockedError
from src.models import MediaKind
from src.schemas.capabilities import CAPABILITY_NAMES, Capabilities

#: Media kind -> the capability names it cannot run without.
MEDIA_KIND_REQUIREMENTS: dict[MediaKind, tuple[str, ...]] = {
    MediaKind.PODCAST: ("ai", "tts"),
    MediaKind.SLIDES: ("ai", "images"),
    MediaKind.INFOGRAPHIC: ("ai", "images"),
    MediaKind.VIDEO: ("ai", "images", "tts"),
    MediaKind.MINDMAP: (),
    MediaKind.REPORT: (),
    MediaKind.COVER_IMAGE: (),
}

# A requirement naming a capability that does not exist would never be checked. Catch it at
# import time, where it is a five-second fix, rather than in production, where it is silence.
for _kind, _required in MEDIA_KIND_REQUIREMENTS.items():
    for _name in _required:
        if _name not in CAPABILITY_NAMES:
            raise RuntimeError(
                f"MEDIA_KIND_REQUIREMENTS[{_kind}] names unknown capability {_name!r}"
            )

#: What a user is told, per capability, when it is missing. No environment variable names
#: and no provider names: this reaches a learner, who can act on none of them. The admin's
#: actionable version is the capability ``hint``, which only the authenticated admin
#: endpoint carries.
_PUBLIC_EXPLANATION: dict[str, str] = {
    "ai": "AI generation is not available in this installation.",
    "images": "Image generation is not available in this installation.",
    "tts": "Voice generation is not available in this installation.",
}


def requirements_payload() -> dict[str, list[str]]:
    """The registry as JSON the frontend can read: ``{"infographic": ["ai", "images"]}``."""
    return {kind.value: list(names) for kind, names in MEDIA_KIND_REQUIREMENTS.items()}


def blocking_capability(kind: MediaKind, capabilities: Capabilities) -> str | None:
    """The first required capability that is BLOCKED, or ``None`` when the kind can run.

    Only ``BLOCKED`` refuses. ``DEGRADED`` means "works, on a lesser path" — refusing it
    would switch the podcast off in every deployment that voices it today through the
    offline eSpeak fallback, which is a working feature, not a broken one.
    """
    for name in MEDIA_KIND_REQUIREMENTS.get(kind, ()):
        capability = getattr(capabilities, name)
        if capability.is_blocked:
            return name
    return None


def ensure_kind_is_available(kind: MediaKind, capabilities: Capabilities) -> None:
    """Raise :class:`CapabilityBlockedError` if this kind cannot be generated here.

    Called before the row is created, so a job that cannot succeed is never accepted: the
    user reads one typed, immediate refusal instead of watching a spinner for thirty
    seconds and then being shown a provider's exception text.
    """
    name = blocking_capability(kind, capabilities)
    if name is None:
        return
    capability = getattr(capabilities, name)
    explanation = _PUBLIC_EXPLANATION.get(
        name, f"{name} is not available in this installation."
    )
    raise CapabilityBlockedError(
        capability=name,
        reason=str(capability.reason) if capability.reason else None,
        message=explanation,
        details={"kind": kind.value},
    )


__all__ = [
    "MEDIA_KIND_REQUIREMENTS",
    "blocking_capability",
    "ensure_kind_is_available",
    "requirements_payload",
]
