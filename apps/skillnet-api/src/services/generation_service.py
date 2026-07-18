"""Generation job orchestration and its background-runner seam."""

import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.core.tasks import task_registry
from src.deps.db import async_session_factory
from src.models import GenerationJob, GenerationOutput, GenerationStep
from src.repositories.generation_job_repo import GenerationJobRepository

logger = get_logger(__name__)


class GenerationService:
    def __init__(self, repo: GenerationJobRepository) -> None:
        self.repo = repo

    async def create_and_start(
        self,
        db: AsyncSession,
        *,
        org_id: uuid.UUID,
        triggered_by: uuid.UUID,
        course_id: uuid.UUID,
        source_document_id: uuid.UUID | None,
        output_type: str,
    ) -> GenerationJob:
        try:
            output = GenerationOutput(output_type)
        except ValueError:
            output = GenerationOutput.COURSE_AND_MANUAL

        job = await self.repo.create(
            org_id=org_id,
            triggered_by=triggered_by,
            source_document_id=source_document_id,
            output_type=output,
            status=GenerationStep.PENDING,
            result_course_id=course_id,
            progress={},
        )
        # The route commits after this returns; the worker tolerates the row not
        # yet being visible via a short retry loop.
        task_registry.spawn(
            run_generation_job(job.id), name=f"generation:{job.id}"
        )
        return job


async def _load_job_with_retry(
    session: AsyncSession, job_id: uuid.UUID
) -> GenerationJob | None:
    repo = GenerationJobRepository(session)
    for _ in range(10):
        job = await repo.get_by_id(job_id)
        if job is not None:
            return job
        await asyncio.sleep(0.2)
    return None


async def run_generation_job(job_id: uuid.UUID) -> None:
    """Background worker: run the Phase 4 pipeline (lazy import) or fail gracefully.

    SEAM: ``src.agents.content.runner`` does not exist until Phase 4.
    """
    try:
        from src.agents.content.runner import run_generation
    except ImportError:
        logger.warning(
            "Generation pipeline unavailable (Phase 4 not built); "
            "marking job %s as failed",
            job_id,
        )
        async with async_session_factory() as session:
            job = await _load_job_with_retry(session, job_id)
            if job is not None:
                repo = GenerationJobRepository(session)
                await repo.update(
                    job,
                    status=GenerationStep.FAILED,
                    error_message="Content generation pipeline is not available yet.",
                )
            await session.commit()
        return

    await run_generation(job_id)
