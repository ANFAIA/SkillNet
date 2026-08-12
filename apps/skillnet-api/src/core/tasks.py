"""Strong-reference registry for fire-and-forget background asyncio tasks."""

import asyncio
from collections.abc import Coroutine
from typing import Any

from src.core.logging import get_logger

logger = get_logger(__name__)


class TaskRegistry:
    """Keeps references to running tasks so the event loop does not GC them."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()

    def spawn(self, coro: Coroutine[Any, Any, Any], name: str) -> asyncio.Task:
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._on_done)
        return task

    def spawn_unique(self, coro: Coroutine[Any, Any, Any], name: str) -> asyncio.Task:
        """Reuse an in-flight named task and close the duplicate coroutine."""
        for task in self._tasks:
            if not task.done() and task.get_name() == name:
                coro.close()
                return task
        return self.spawn(coro, name)

    def _on_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("Background task %s failed: %s", task.get_name(), exc)


task_registry = TaskRegistry()
