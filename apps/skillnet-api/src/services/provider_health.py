"""Recent provider failures, remembered just long enough to be useful.

The config layer of ``services.capabilities`` answers "is a key configured". This module
answers the other half: "did the provider actually work a minute ago". A key that is
present but out of quota looks perfect to a pure config read, so without this the UI keeps
offering a button that has failed on its last five attempts.

It is a plain in-process dictionary with a TTL. Three properties matter:

* **Single worker.** Same assumption as ``_INFLIGHT`` in ``services.node_render_service``:
  the deployment runs one uvicorn worker, so one process sees every failure. Under several
  workers each would keep its own view — degraded to the config-only answer for the workers
  that did not see the failure, never wrong, just less informed.
* **Self-healing.** Entries expire after :data:`FAILURE_TTL_SECONDS` and the whole registry
  dies with the process, so a provider that comes back is trusted again without anyone
  clearing anything. That is why the TTL is minutes and not hours.
* **Never raises, never blocks.** Every entry point is called from an ``except`` block on
  the hot path. A bookkeeping error there would replace a provider's failure with our own,
  so the recorder swallows everything. No I/O, no locks, no awaits.

The "provider" is the *provider slot* a capability draws on — ``llm``, ``images``, ``tts``
— and not a vendor name. This app configures exactly one provider per slot, so the slot is
the only granularity anything can act on.
"""

from __future__ import annotations

import time
from typing import Literal

from src.schemas.capabilities import CapabilityReason

#: How long a recorded failure keeps counting against a provider. Long enough to cover the
#: minute-long quota windows the LLM retry logic already reasons about, short enough that a
#: provider which recovers is offered again without a restart.
FAILURE_TTL_SECONDS = 600.0

FailureKind = Literal["quota", "down"]

#: The provider slots this registry knows. Recording an unknown slot is ignored rather than
#: raised — see the module docstring on never failing a caller's ``except`` block.
LLM = "llm"
IMAGES = "images"
TTS = "tts"
PROVIDERS: tuple[str, ...] = (LLM, IMAGES, TTS)

_REASON_FOR: dict[str, CapabilityReason] = {
    "quota": CapabilityReason.PROVIDER_QUOTA,
    "down": CapabilityReason.PROVIDER_DOWN,
}

#: ``(provider, kind) -> monotonic deadline``. Recording the same failure again simply
#: pushes its deadline out, which is the behaviour we want: a provider that keeps failing
#: keeps counting as failing.
_FAILURES: dict[tuple[str, str], float] = {}


def record_failure(provider: str, kind: FailureKind) -> None:
    """Remember that ``provider`` just failed this way. Never raises."""
    try:
        if provider not in PROVIDERS or kind not in _REASON_FOR:
            return
        _FAILURES[(provider, kind)] = time.monotonic() + FAILURE_TTL_SECONDS
    except Exception:  # noqa: BLE001 - bookkeeping must never displace the real failure
        return


def status_for(provider: str) -> tuple[CapabilityReason, ...] | None:
    """The unexpired reasons recorded against ``provider``, or ``None`` if it looks healthy.

    Quota comes first when both are recorded: "you are out of credit" is the more
    actionable of the two, and a provider that 429s often times out too.
    """
    try:
        now = time.monotonic()
        reasons = [
            _REASON_FOR[kind]
            for kind in ("quota", "down")
            if _FAILURES.get((provider, kind), 0.0) > now
        ]
        return tuple(reasons) or None
    except Exception:  # noqa: BLE001 - a capability read must never fail on bookkeeping
        return None


def failure_kind(exc: BaseException) -> FailureKind:
    """Classify a provider exception as ``quota`` (429/402) or ``down`` (everything else).

    The status is read off the exception itself, and off the exception it was chained from
    — the TTS providers normalize ``httpx.HTTPStatusError`` into a ``RuntimeError`` with
    ``raise ... from exc``, so the real status survives on ``__cause__``. Nothing is parsed
    out of a message: a message is prose, and guessing at it would invent a quota failure
    out of a provider that merely said the word "rate" somewhere.
    """
    try:
        for candidate in (exc, getattr(exc, "__cause__", None)):
            if candidate is None:
                continue
            if _status_of(candidate) in (402, 429):
                return "quota"
            # litellm normalizes every provider's 429 to RateLimitError, and it does not
            # always carry a status code.
            if type(candidate).__name__ == "RateLimitError":
                return "quota"
    except Exception:  # noqa: BLE001 - classification must never raise
        return "down"
    return "down"


def _status_of(exc: BaseException) -> int | None:
    """The HTTP status an exception carries, under any of the names in use."""
    for attribute in ("status_code", "http_status", "code"):
        value = getattr(exc, attribute, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def reset() -> None:
    """Forget every recorded failure. For tests, and for nothing else."""
    _FAILURES.clear()


__all__ = [
    "FAILURE_TTL_SECONDS",
    "IMAGES",
    "LLM",
    "PROVIDERS",
    "TTS",
    "FailureKind",
    "failure_kind",
    "record_failure",
    "reset",
    "status_for",
]
