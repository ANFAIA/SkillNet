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


class Subscription:
    """A subscription that is registered the moment it is constructed.

    :func:`subscribe` is an async generator, and an async generator body does not run
    until its first ``__anext__`` — so ``subscribe(channel)`` on its own registers
    nothing, and any event published between that call and the first await is dropped.
    That is invisible for a consumer that immediately starts iterating, but it makes
    "register, then read the current state, then stream" impossible to write correctly:
    the read sits inside the very window the registration was supposed to close.

    Constructing this registers the queue eagerly, so the caller can do work before it
    starts consuming and still receive everything published meanwhile.
    """

    def __init__(self, channel: str) -> None:
        self.channel = channel
        self.queue: asyncio.Queue = asyncio.Queue()
        _registry.setdefault(channel, []).append(self.queue)
        self._closed = False

    async def get(self) -> dict:
        """The next event, waiting for one if the queue is empty."""
        return await self.queue.get()

    def close(self) -> None:
        """Deregister. Idempotent, so a ``finally`` can always call it."""
        if self._closed:
            return
        self._closed = True
        subscribers = _registry.get(self.channel)
        if subscribers is not None:
            try:
                subscribers.remove(self.queue)
            except ValueError:
                pass
            if not subscribers:
                _registry.pop(self.channel, None)


async def subscribe(channel: str) -> AsyncIterator[dict]:
    """Yield ``{"type", "data"}`` events until the consumer stops iterating."""
    subscription = Subscription(channel)
    try:
        while True:
            yield await subscription.get()
    finally:
        subscription.close()


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
