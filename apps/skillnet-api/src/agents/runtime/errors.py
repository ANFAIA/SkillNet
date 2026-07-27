"""Per-node error handling for the runtime render graph (§4.2).

**Independent from ``src/agents/content/errors.py`` on purpose, and this is not stylistic.**
The v1 wrapper is hard-wired to ``state["job_id"]`` and to marking a ``generation_jobs`` row
``failed``; ``NodeRuntimeState`` has neither. With an empty ``job_id`` the v1 wrapper skips
**both** the bookkeeping **and** the ``sse.publish``, so the ``error {fallback: true}``
contract the frontend waits for in §9.2 would never be emitted on a node failure — the
learner would sit in front of a skeleton forever.

What this wrapper does on an exception:

1. ``node_renders.status = 'failed'`` with the message, **if a row was already claimed**.
   Before ``load_context`` finishes there is no row and there is nothing to mark; the SSE
   event still goes out, which is the part the client depends on.
2. ``sse.publish(f"node:{request_id}", "error", {step, message, fallback: True})``.
   ``fallback: True`` tells the client to re-request the render and take the seed.
3. Returns ``{"error": ..., "current_step": "failed"}`` so the graph short-circuits instead
   of letting the next node run on a half-built state.

``asyncio.CancelledError`` is **re-raised untouched**: a cancelled render is the designed
outcome of §9.1 (the probe closed as ``mastered`` while generation was in flight), not a
failure, and swallowing it here would turn a cancellation into a phantom ``error`` event.
"""

from __future__ import annotations

import asyncio
import functools
import uuid
from collections.abc import Awaitable, Callable

from src.agents.runtime.state import NodeRuntimeState
from src.core import sse
from src.core.logging import get_logger
from src.deps.db import async_session_factory
from src.repositories.node_render_repo import NodeRenderRepository

logger = get_logger(__name__)

RuntimeNodeFn = Callable[[NodeRuntimeState], Awaitable[dict]]

#: How much of an exception message reaches the browser. The full text goes to the log.
_CLIENT_MESSAGE_CHARS = 200
_STORED_MESSAGE_CHARS = 500


def node_channel(request_id: str | uuid.UUID) -> str:
    """The SSE channel of one render request (§9.2). Never shared with v1's
    ``generation:{job_id}``: the audiences and the event families are disjoint."""
    return f"node:{request_id}"


async def publish_step(request_id: str, step: str, message: str) -> None:
    """``render_step`` — emitted on entering each node of the graph (§9.2)."""
    await sse.publish(
        node_channel(request_id), "render_step", {"step": step, "message": message}
    )


async def publish_error(
    request_id: str, step: str, message: str, *, fallback: bool = True
) -> None:
    """``error {step, message, fallback}`` — the contract of §9.2."""
    await sse.publish(
        node_channel(request_id),
        "error",
        {
            "step": step,
            "message": message[:_CLIENT_MESSAGE_CHARS],
            "fallback": fallback,
        },
    )


async def mark_render_failed(render_id: str | None, message: str) -> None:
    """Best-effort ``node_renders.status = 'failed'``. Never raises.

    Its own session: the failing node's session is unusable (it may hold the exception
    that got us here), and bookkeeping that fails because the thing it records failed is
    no bookkeeping at all.
    """
    if not render_id:
        return
    try:
        async with async_session_factory() as db:
            await NodeRenderRepository(db).fail_by_id(
                uuid.UUID(str(render_id)), message[:_STORED_MESSAGE_CHARS]
            )
            await db.commit()
    except Exception:  # noqa: BLE001 - failure bookkeeping must never raise
        logger.error("Failed to mark render %s as failed", render_id, exc_info=True)


def runtime_node_error_wrapper(name: str) -> Callable[[RuntimeNodeFn], RuntimeNodeFn]:
    """Wrap a runtime node so any exception is recorded, announced and short-circuited."""

    def decorator(func: RuntimeNodeFn) -> RuntimeNodeFn:
        @functools.wraps(func)
        async def wrapper(state: NodeRuntimeState) -> dict:
            try:
                return await func(state)
            except asyncio.CancelledError:
                # §9.1: the probe mastered the node while this was in flight. Not an error.
                raise
            except Exception as exc:  # noqa: BLE001 - node boundary catch-all
                logger.error("Runtime node '%s' failed: %s", name, exc, exc_info=True)
                message = f"[{name}] {type(exc).__name__}: {str(exc)[:_STORED_MESSAGE_CHARS]}"
                request_id = str(state.get("request_id", ""))
                await mark_render_failed(state.get("render_id"), message)
                if request_id:
                    await publish_error(request_id, name, str(exc), fallback=True)
                return {"error": message, "current_step": "failed"}

        return wrapper

    return decorator


__all__ = [
    "mark_render_failed",
    "node_channel",
    "publish_error",
    "publish_step",
    "runtime_node_error_wrapper",
]
