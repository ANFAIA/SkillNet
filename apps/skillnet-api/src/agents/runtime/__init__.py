"""The runtime render pipeline of §4.2 — one compiled graph per node render.

Public surface, and the only names the rest of the backend should import:

* :func:`~src.agents.runtime.graph.build_node_graph` — the compiled graph.
* :func:`~src.agents.runtime.runner.run_node_render` / ``spawn_node_render`` — how a route
  starts one (subscriber wait, concurrency ceiling, cancellation).
* :class:`~src.agents.runtime.state.NodeRuntimeState` — the state the nodes exchange.
* :func:`~src.agents.runtime.router.select_tier` / ``purpose_for`` — the two-tier router of
  §4.3, connected to ``resolve_llm_config`` and to nothing provider-specific.
* :func:`~src.agents.runtime.errors.runtime_node_error_wrapper` — the per-node wrapper, which
  is **not** the v1 one (see that module's docstring for the concrete reason).
"""

from src.agents.runtime.errors import (
    mark_render_failed,
    node_channel,
    runtime_node_error_wrapper,
)
from src.agents.runtime.graph import build_node_graph
from src.agents.runtime.router import (
    ALLOWED_UI_FORMATS,
    HEAVY_FORMATS,
    coerce_ui_format,
    purpose_for,
    runtime_model_key,
    select_tier,
)
from src.agents.runtime.runner import (
    RUNTIME_CONCURRENCY,
    run_node_render,
    spawn_node_render,
)
from src.agents.runtime.state import NodeRuntimeState

__all__ = [
    "ALLOWED_UI_FORMATS",
    "HEAVY_FORMATS",
    "RUNTIME_CONCURRENCY",
    "NodeRuntimeState",
    "build_node_graph",
    "coerce_ui_format",
    "mark_render_failed",
    "node_channel",
    "purpose_for",
    "run_node_render",
    "runtime_model_key",
    "runtime_node_error_wrapper",
    "select_tier",
    "spawn_node_render",
]
