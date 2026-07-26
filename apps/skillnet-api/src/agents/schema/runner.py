"""Entry point for the schema proposal background job.

Mirrors ``src/agents/content/runner.py``: load the job, build the initial state,
drive the compiled graph, and guarantee a terminal job status even if the graph
returns without persisting.
"""

from __future__ import annotations

import asyncio
import uuid

from src.agents.schema.errors import mark_job_failed, sse_channel
from src.agents.schema.graph import build_schema_graph
from src.agents.schema.state import SchemaState
from src.core import sse
from src.core.logging import get_logger
from src.deps.db import async_session_factory
from src.models import GenerationJob, GenerationStep
from src.repositories.generation_job_repo import GenerationJobRepository

logger = get_logger(__name__)

DEFAULT_INTENT_DENSITY = 3


async def _load_job(job_id: uuid.UUID) -> GenerationJob | None:
    """Load the job, tolerating the creating transaction not yet being visible."""
    for _ in range(10):
        async with async_session_factory() as db:
            job = await GenerationJobRepository(db).get_by_id(job_id)
            if job is not None:
                return job
        await asyncio.sleep(0.2)
    return None


def initial_state(job: GenerationJob) -> SchemaState:
    progress = dict(job.progress or {})
    try:
        density = int(progress.get("intent_density") or DEFAULT_INTENT_DENSITY)
    except (TypeError, ValueError):
        density = DEFAULT_INTENT_DENSITY
    return {
        "job_id": str(job.id),
        "org_id": str(job.org_id),
        "triggered_by": str(job.triggered_by),
        "source_document_ids": (
            [str(job.source_document_id)] if job.source_document_id else []
        ),
        "course_id": str(job.result_course_id) if job.result_course_id else "",
        "intent_density": max(1, min(density, 5)),
        "proposed_nodes": [],
        "schema_warnings": [],
        "current_step": "pending",
        "error": None,
    }


async def run_schema_proposal(job_id: str | uuid.UUID) -> None:
    """Run the full schema proposal pipeline for ``job_id``."""
    jid = uuid.UUID(str(job_id))
    logger.info("Starting schema proposal run for job %s", jid)

    job = await _load_job(jid)
    if job is None:
        logger.error("Schema job %s not found; aborting run", jid)
        return
    if not job.result_course_id:
        # Without a course there is nothing to attach nodes to; fail loudly rather
        # than create an orphan schema.
        await mark_job_failed(str(jid), "Schema job has no target course.")
        return

    try:
        graph = build_schema_graph()
        await graph.ainvoke(
            initial_state(job),
            config={"configurable": {"thread_id": str(jid)}},
        )
    except Exception as exc:  # noqa: BLE001 - top-level safety net
        logger.error("Schema run %s failed: %s", jid, exc, exc_info=True)
        await mark_job_failed(str(jid), f"{type(exc).__name__}: {str(exc)[:500]}")
        await sse.publish(
            sse_channel(str(jid)),
            "error",
            {"step": "runner", "message": str(exc)[:200]},
        )
        return

    async with async_session_factory() as db:
        repo = GenerationJobRepository(db)
        current = await repo.get_by_id(jid)
        if current is not None and current.status not in (
            GenerationStep.SCHEMA_PROPOSED,
            GenerationStep.FAILED,
        ):
            await repo.update(
                current,
                status=GenerationStep.FAILED,
                error_message="Schema run ended without proposing a schema.",
            )
        await db.commit()

    logger.info("Schema proposal run for job %s finished", jid)
