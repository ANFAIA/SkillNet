"""Entry point invoked by the Phase 3 background seam.

``run_generation`` loads the generation job, builds the initial graph state, and
drives the compiled LangGraph to completion. On any failure it marks the job
failed and emits an SSE error event.
"""

from __future__ import annotations

import asyncio
import uuid

from src.agents.content.errors import mark_job_failed, sse_channel
from src.agents.content.graph import build_content_graph
from src.agents.content.state import GenerationState
from src.core import sse
from src.core.logging import get_logger
from src.deps.db import async_session_factory
from src.models import GenerationJob, GenerationStep
from src.repositories.generation_job_repo import GenerationJobRepository

logger = get_logger(__name__)


async def _load_job(job_id: uuid.UUID) -> GenerationJob | None:
    """Load the job, tolerating the creating transaction not yet being visible."""
    for _ in range(10):
        async with async_session_factory() as db:
            job = await GenerationJobRepository(db).get_by_id(job_id)
            if job is not None:
                return job
        await asyncio.sleep(0.2)
    return None


def _initial_state(job: GenerationJob) -> GenerationState:
    source_ids = [str(job.source_document_id)] if job.source_document_id else []
    return {
        "job_id": str(job.id),
        "org_id": str(job.org_id),
        "triggered_by": str(job.triggered_by),
        "source_document_ids": source_ids,
        "course_id": str(job.result_course_id) if job.result_course_id else None,
        "refinement_count": 0,
        "current_step": "pending",
        "error": None,
    }


async def run_generation(job_id: str | uuid.UUID) -> None:
    """Run the full content generation pipeline for ``job_id``."""
    jid = uuid.UUID(str(job_id))
    logger.info("Starting generation run for job %s", jid)

    job = await _load_job(jid)
    if job is None:
        logger.error("Generation job %s not found; aborting run", jid)
        return

    initial_state = _initial_state(job)

    try:
        graph = build_content_graph()
        await graph.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": str(jid)}},
        )
    except Exception as exc:  # noqa: BLE001 - top-level safety net
        logger.error("Generation run %s failed: %s", jid, exc, exc_info=True)
        await mark_job_failed(str(jid), f"{type(exc).__name__}: {str(exc)[:500]}")
        await sse.publish(
            sse_channel(str(jid)), "error", {"step": "runner", "message": str(exc)[:200]}
        )
        return

    # Ensure a terminal status even if the graph ended without publishing
    # (e.g. handle_error path already set failed; this only fills gaps).
    async with async_session_factory() as db:
        repo = GenerationJobRepository(db)
        current = await repo.get_by_id(jid)
        if current is not None and current.status not in (
            GenerationStep.PUBLISHED,
            GenerationStep.FAILED,
        ):
            await repo.update(
                current,
                status=GenerationStep.FAILED,
                error_message="Generation ended without publishing.",
            )
        await db.commit()

    logger.info("Generation run for job %s finished", jid)
