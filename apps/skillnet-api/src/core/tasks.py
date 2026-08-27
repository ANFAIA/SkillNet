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

    def has_running(self, name: str) -> bool:
        """Is a task with exactly this name still running?

        The registry already reuses a named task inside :meth:`spawn_unique`, but a
        caller sometimes has to know *before* it builds the coroutine — the course
        finalization endpoint has to decide whether to re-claim the row and spawn, or
        report the run already in flight, and it cannot answer that by constructing a
        coroutine it may have to throw away.
        """
        return any(
            not task.done() and task.get_name() == name for task in self._tasks
        )

    def cancel_by_prefix(self, prefix: str) -> int:
        """Cancel every still-running task whose name starts with ``prefix``.

        Used to supersede a superseded background job cleanly: when a newer run for the
        same subject starts, the older one is cancelled instead of being left to race
        the new one to the same rows.
        """
        cancelled = 0
        for task in list(self._tasks):
            if not task.done() and task.get_name().startswith(prefix):
                task.cancel()
                cancelled += 1
        return cancelled

    def _on_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("Background task %s failed: %s", task.get_name(), exc)


task_registry = TaskRegistry()
