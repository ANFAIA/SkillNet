"""The two-tier runtime router (§4.3).

Routing happens **at the level of the whole screen**, not per component: one
``ui_format`` decision picks one tier, and that tier generates the whole program. A
per-component router would multiply the number of calls by the number of blocks, which is
the opposite of the reason the cheap tier exists.

Everything here is a pure function over strings. The provider machinery is
``resolve_llm_config(org_settings, purpose=...)``, untouched: the two purposes
``runtime_fast`` / ``runtime_heavy`` resolve through the precedence it already implements
(``src/llm/client.py``)::

    org_settings["llm_runtime_fast_model"]
      -> org_settings["llm_model"]
      -> settings.LLM_RUNTIME_FAST_MODEL
      -> settings.LLM_MODEL

so with nothing configured **both tiers fall back to ``LLM_MODEL``** and the whole feature
works with a single model. No provider is a requirement and none is named anywhere in this
package: everything goes through litellm.
"""

from __future__ import annotations

import enum
from typing import Any, Literal

from src.llm.client import LLMConfig, resolve_llm_config
from src.llm.fixtures import maybe_fixture_llm

Tier = Literal["fast", "heavy"]

#: Formats worth the expensive model: they need structured data (``chart``), two kinds of
#: block at once (``mixed``), or a form the kit cannot even express (``simulation``, kept
#: here so the mapping stays total against the ``ui_format`` enum).
HEAVY_FORMATS: frozenset[str] = frozenset({"chart", "mixed", "simulation"})

#: What ``decide_formato`` may return. ``simulation`` is OFF in this PR (§1.3): there is no
#: component in the frozen kit that could render one.
ALLOWED_UI_FORMATS: frozenset[str] = frozenset(
    {"explanation", "exercise", "chart", "mixed"}
)

# There is deliberately no FAST_FORMATS: ``select_tier`` only ever consults HEAVY_FORMATS,
# so a second constant would be dead code that can drift out of sync with the first.

FAST_PURPOSE = "runtime_fast"
HEAVY_PURPOSE = "runtime_heavy"

#: The default when the model returns something unusable, and the value used during the
#: calibration period before ``node.default_ui_format`` is known to the caller.
DEFAULT_UI_FORMAT = "explanation"


def _plain(value: object) -> str:
    """Enum member or raw string -> its string value."""
    return value.value if isinstance(value, enum.Enum) else str(value)


def select_tier(ui_format: object) -> Tier:
    """``"heavy"`` for the three formats that need the room, ``"fast"`` otherwise."""
    return "heavy" if _plain(ui_format) in HEAVY_FORMATS else "fast"


def purpose_for(tier: object) -> str:
    """``"runtime_heavy"`` / ``"runtime_fast"`` — the ``purpose`` of ``resolve_llm_config``."""
    return HEAVY_PURPOSE if _plain(tier) == "heavy" else FAST_PURPOSE


def coerce_ui_format(raw: object, default: object = DEFAULT_UI_FORMAT) -> str:
    """Clamp anything the model said into :data:`ALLOWED_UI_FORMATS`.

    ``simulation`` is treated as unusable like any other unknown value: it is a member of
    the ``ui_format`` enum (so it can be stored) but nothing can render it, and quietly
    accepting it would produce a screen the browser has no component for.
    """
    candidate = _plain(raw).strip().lower()
    if candidate in ALLOWED_UI_FORMATS:
        return candidate
    fallback = _plain(default).strip().lower()
    if fallback in ALLOWED_UI_FORMATS:
        return fallback
    return DEFAULT_UI_FORMAT


def tier_config(
    org_settings: dict[str, Any] | None, tier: object
) -> LLMConfig:
    """Resolve the connection settings for one tier. Nothing is hardcoded per provider."""
    return resolve_llm_config(org_settings or {}, purpose=purpose_for(tier))


def tier_llm(org_settings: dict[str, Any] | None, tier: object) -> Any:
    """The ``LLMService`` for one tier, through the single fixture branch point (§12.1)."""
    return maybe_fixture_llm(tier_config(org_settings, tier))


def runtime_model_key(org_settings: dict[str, Any] | None) -> str:
    """The ``model`` component of the ``cache_key`` (§3.4): ``"<fast>|<heavy>"``.

    Why both, and why not "the model that generated it": the cache lookup has to happen
    **before** the graph runs (§4.2), and the tier is only known after ``decide_formato``
    has chosen a format — so the key cannot contain the model that will end up generating.
    Pinning both model ids keeps the invariant that actually matters: changing either
    configured model invalidates every cached render, instead of silently serving a
    program written by a model that is no longer in use.
    """
    fast = tier_config(org_settings, "fast").model
    heavy = tier_config(org_settings, "heavy").model
    return f"{fast}|{heavy}"


__all__ = [
    "ALLOWED_UI_FORMATS",
    "DEFAULT_UI_FORMAT",
    "FAST_PURPOSE",
    "HEAVY_FORMATS",
    "HEAVY_PURPOSE",
    "Tier",
    "coerce_ui_format",
    "purpose_for",
    "runtime_model_key",
    "select_tier",
    "tier_config",
    "tier_llm",
]
