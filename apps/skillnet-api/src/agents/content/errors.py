"""Per-node error handling for the generation graph.

Every node is wrapped so a raised exception becomes a clean terminal failure:
the job row is marked ``failed``, an SSE ``error`` event is published, and the
node returns an error state instead of crashing the whole graph invocation.
"""

from __future__ import annotations

import functools
import uuid
from collections.abc import Awaitable, Callable

from src.agents.content.state import GenerationState
from src.core import sse
from src.core.logging import get_logger
from src.deps.db import async_session_factory
from src.models import GenerationStep
from src.repositories.generation_job_repo import GenerationJobRepository

logger = get_logger(__name__)

NodeFn = Callable[[GenerationState], Awaitable[dict]]


def sse_channel(job_id: str) -> str:
    return f"generation:{job_id}"


async def mark_job_failed(job_id: str, error_message: str) -> None:
    """Best-effort update of the generation job row to ``failed``."""
    try:
        async with async_session_factory() as db:
            repo = GenerationJobRepository(db)
            job = await repo.get_by_id(uuid.UUID(str(job_id)))
            if job is not None:
                await repo.update(
                    job,
                    status=GenerationStep.FAILED,
                    error_message=error_message[:2000],
                )
            await db.commit()
    except Exception:  # noqa: BLE001 - failure bookkeeping must never raise
        logger.error("Failed to mark job %s as failed", job_id, exc_info=True)


def node_error_wrapper(name: str) -> Callable[[NodeFn], NodeFn]:
    """Wrap a node so any exception is caught, recorded, and surfaced via SSE."""

    def decorator(func: NodeFn) -> NodeFn:
        @functools.wraps(func)
        async def wrapper(state: GenerationState) -> dict:
            try:
                return await func(state)
            except Exception as exc:  # noqa: BLE001 - node boundary catch-all
                logger.error("Node '%s' failed: %s", name, exc, exc_info=True)
                message = f"[{name}] {type(exc).__name__}: {str(exc)[:500]}"
                job_id = str(state.get("job_id", ""))
                if job_id:
                    await mark_job_failed(job_id, message)
                    await sse.publish(
                        sse_channel(job_id),
                        "error",
                        {"step": name, "message": str(exc)[:200]},
                    )
                return {"error": message, "current_step": "failed"}

        return wrapper

    return decorator
