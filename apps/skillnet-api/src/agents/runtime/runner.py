"""Entry point for one background node render (§4.2, §9.1, §9.2).

Three responsibilities the graph itself must not have:

1. **Wait for the SSE subscriber.** ``POST /nodes/{id}/render`` answers ``202 {request_id}``,
   the client subscribes, and only then does the real work start —
   ``sse.wait_for_subscriber(channel, 0.5)``. This pub/sub keeps no backlog (§9.2), so
   without the wait ``render_step`` and even ``ui_format`` are published into the void and
   the browser sits on a skeleton it cannot replace. A timeout is **not** a failure: the
   render proceeds and the client picks it up from ``GET /nodes/{id}/render``.
2. **Bound the concurrency.** ``asyncio.Semaphore(6)``, process-wide: a shift change where
   forty employees open their first node must not put forty simultaneous generations on one
   uvicorn worker. Six is the number §4.2 fixes.
3. **Handle cancellation.** §9.1 cancels the in-flight render when the probe verdict finally
   comes out ``mastered``. The task is cancelled from
   ``NodeRenderService.cancel``; here the ``CancelledError`` is recorded on the row and
   **re-raised**, because a swallowed cancellation is a task that reports success for work it
   did not do.
"""

from __future__ import annotations

import asyncio
from typing import Any

from src.agents.runtime.errors import mark_render_failed, node_channel
from src.agents.runtime.graph import build_node_graph
from src.agents.runtime.state import NodeRuntimeState
from src.core import sse
from src.core.logging import get_logger
from src.core.tasks import task_registry

logger = get_logger(__name__)

#: Global ceiling on simultaneous runtime generations (§4.2).
RUNTIME_CONCURRENCY = 6

#: How long the runner waits for the client to open the stream before starting (§9.2).
SUBSCRIBER_WAIT_SECONDS = 0.5

_semaphore: asyncio.Semaphore | None = None


def _gate() -> asyncio.Semaphore:
    """Lazily created so importing this module does not need a running event loop."""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(RUNTIME_CONCURRENCY)
    return _semaphore


async def run_node_render(state: NodeRuntimeState | dict[str, Any]) -> dict:
    """Drive the compiled graph for one render request.

    Returns the final graph state. Never raises for a *content* failure — the graph routes
    those to ``fallback_seed`` — but does propagate ``CancelledError``.
    """
    request_id = str(state.get("request_id") or "")
    channel = node_channel(request_id)

    if request_id:
        subscribed = await sse.wait_for_subscriber(channel, SUBSCRIBER_WAIT_SECONDS)
        if not subscribed:
            logger.info(
                "No SSE subscriber on %s after %.2fs; generating anyway",
                channel,
                SUBSCRIBER_WAIT_SECONDS,
            )

    async with _gate():
        try:
            graph = build_node_graph()
            final = await graph.ainvoke(
                dict(state),
                config={"configurable": {"thread_id": request_id or "node-render"}},
            )
        except asyncio.CancelledError:
            # §9.1: the probe mastered the node. Release the cache_key so the row does not
            # sit in `generating` forever blocking its own key, then let the cancellation
            # propagate — the caller asked for it.
            await mark_render_failed(
                state.get("render_id"), "cancelled: the probe closed as mastered"
            )
            logger.info("Render %s cancelled", request_id)
            raise
        except Exception as exc:  # noqa: BLE001 - top-level safety net, mirrors v1's runner
            logger.error("Render run %s failed: %s", request_id, exc, exc_info=True)
            await mark_render_failed(
                state.get("render_id"), f"{type(exc).__name__}: {str(exc)[:500]}"
            )
            await sse.publish(
                channel,
                "error",
                {"step": "runner", "message": str(exc)[:200], "fallback": True},
            )
            return {"error": str(exc), "current_step": "failed"}

    if final.get("error"):
        logger.warning(
            "Render %s finished at step %s with an error: %s",
            request_id,
            final.get("current_step"),
            final.get("error"),
        )
    return dict(final)


def spawn_node_render(state: NodeRuntimeState | dict[str, Any]) -> asyncio.Task:
    """Fire the render off as a tracked background task.

    ``task_registry`` keeps the strong reference (an unreferenced task can be garbage
    collected mid-await) and logs a failure that escapes; the returned handle is what makes
    the cancellation of §9.1 possible.
    """
    request_id = str(state.get("request_id") or "unknown")
    return task_registry.spawn(run_node_render(state), name=f"node-render:{request_id}")


__all__ = [
    "RUNTIME_CONCURRENCY",
    "SUBSCRIBER_WAIT_SECONDS",
    "run_node_render",
    "spawn_node_render",
]
