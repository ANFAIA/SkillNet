"""The admin-agent tool catalog: one flat registry, populated by domain modules.

The agent loop (``src/services/admin_agent_service.py``) only ever talks to this
module — it never imports ``users.py``/``enrollment.py`` directly, so adding a
new domain module is the only change needed to grow the catalog.
"""

from __future__ import annotations

from src.services.agent_tools.base import ToolSpec
from src.services.agent_tools import enrollment, users

_ALL_TOOLS: tuple[ToolSpec, ...] = (*users.TOOLS, *enrollment.TOOLS)

REGISTRY: dict[str, ToolSpec] = {tool.name: tool for tool in _ALL_TOOLS}

if len(REGISTRY) != len(_ALL_TOOLS):
    # A duplicate tool name is a programming error in a domain module, not
    # something to discover at runtime via a silently-shadowed handler.
    seen: set[str] = set()
    for tool in _ALL_TOOLS:
        if tool.name in seen:
            raise ValueError(f"Duplicate tool name registered: {tool.name}")
        seen.add(tool.name)


def get(name: str) -> ToolSpec | None:
    return REGISTRY.get(name)


def provider_schemas() -> list[dict]:
    """The ``tools=[...]`` payload for every registered tool.

    Six tools today is small enough to send whole; the ``domain``/``verb``
    fields on :class:`ToolSpec` are what a future filtered/dynamic subset
    (per-domain retrieval) would key off, without changing this function's
    callers.
    """
    return [tool.as_provider_schema() for tool in REGISTRY.values()]
