"""Generic in-process SSE pub/sub shared by generation and chat streaming."""

import asyncio
import json
import time
from collections.abc import AsyncIterator

from src.core.logging import get_logger

logger = get_logger(__name__)

_registry: dict[str, list[asyncio.Queue]] = {}

#: How often :func:`wait_for_subscriber` re-checks the registry.
SUBSCRIBER_POLL_SECONDS = 0.025


async def publish(channel: str, event_type: str, data: dict) -> None:
    """Fan out an event to every subscriber currently listening on ``channel``."""
    event = {"type": event_type, "data": data}
    for queue in list(_registry.get(channel, [])):
        queue.put_nowait(event)


async def subscribe(channel: str) -> AsyncIterator[dict]:
    """Yield ``{"type", "data"}`` events until the consumer stops iterating."""
    queue: asyncio.Queue = asyncio.Queue()
    _registry.setdefault(channel, []).append(queue)
    try:
        while True:
            event = await queue.get()
            yield event
    finally:
        subscribers = _registry.get(channel)
        if subscribers is not None:
            try:
                subscribers.remove(queue)
            except ValueError:
                pass
            if not subscribers:
                _registry.pop(channel, None)


def subscriber_count(channel: str) -> int:
    """How many consumers are listening on ``channel`` right now (§9.2).

    Added because ``_registry`` is private and had no accessor, so the mitigation this
    module's known limitation needs — "wait until somebody is listening before doing the
    expensive work" — could not be written at all. Events published to a channel with
    zero subscribers are dropped on the floor.
    """
    return len(_registry.get(channel, ()))


async def wait_for_subscriber(channel: str, timeout: float = 0.5) -> bool:
    """``True`` if a subscriber appears before ``timeout``. Polls every 25 ms (§9.2).

    The runtime render flow is ``202 {request_id}`` -> client subscribes -> worker
    starts. Without this wait the worker can publish ``render_step`` and even
    ``ui_format`` before the browser has opened the stream, and those events are lost
    forever (this pub/sub keeps no backlog). A **timeout is not a failure**: the caller
    proceeds anyway, because a client that never subscribes must not block generation —
    it will pick the render up from ``GET /nodes/{id}/render``.
    """
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        if subscriber_count(channel):
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return subscriber_count(channel) > 0
        await asyncio.sleep(min(SUBSCRIBER_POLL_SECONDS, remaining))


def format_sse(event_type: str, data: dict) -> str:
    """Serialize one event into the SSE wire format."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
