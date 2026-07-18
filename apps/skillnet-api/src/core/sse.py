"""Generic in-process SSE pub/sub shared by generation and chat streaming."""

import asyncio
import json
from collections.abc import AsyncIterator

from src.core.logging import get_logger

logger = get_logger(__name__)

_registry: dict[str, list[asyncio.Queue]] = {}


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


def format_sse(event_type: str, data: dict) -> str:
    """Serialize one event into the SSE wire format."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
