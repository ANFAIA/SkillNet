"""Per-node error handling for the schema proposal graph.

Independent from ``src/agents/content/errors.py`` on purpose: the v1 wrapper is
tied to v1 job states and publishes generic ``step`` events. This one emits the
``schema_*`` event family.

**The SSE channel is shared with v1** (``generation:{job_id}``) and that is
deliberate: ``src/routes/generation_jobs.py`` hardcodes that channel, so a private
``schema:{job_id}`` channel would reach no client. Collisions are impossible
because the event *types* are namespaced (``schema_step``, ``schema_progress``,
``schema_ready``) and v1 never emits them.
"""

from __future__ import annotations

import functools
import uuid
from collections.abc import Awaitable, Callable

from src.agents.schema.state import SchemaState
from src.core import sse
from src.core.logging import get_logger
from src.deps.db import async_session_factory
from src.models import GenerationStep
from src.repositories.generation_job_repo import GenerationJobRepository

logger = get_logger(__name__)

SchemaNodeFn = Callable[[SchemaState], Awaitable[dict]]


def sse_channel(job_id: str) -> str:
    """Same channel as v1 — see the module docstring."""
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
        logger.error("Failed to mark schema job %s as failed", job_id, exc_info=True)


def schema_node_error_wrapper(name: str) -> Callable[[SchemaNodeFn], SchemaNodeFn]:
    """Wrap a node so any exception is caught, recorded, and surfaced via SSE."""

    def decorator(func: SchemaNodeFn) -> SchemaNodeFn:
        @functools.wraps(func)
        async def wrapper(state: SchemaState) -> dict:
            try:
                return await func(state)
            except Exception as exc:  # noqa: BLE001 - node boundary catch-all
                logger.error("Schema node '%s' failed: %s", name, exc, exc_info=True)
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
