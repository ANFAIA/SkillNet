"""Generation job data access."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import GenerationJob, GenerationStep
from src.repositories.base import BaseRepository

# Statuses a *schema* job can be in while it is still running. Everything else is
# terminal for it: ``schema_proposed`` (done) and ``failed``. A row with
# ``cancelled_at`` set is terminal too, whatever its status says.
#
# ``pending`` is deliberately NOT here even though it is non-terminal: v1 content
# generation creates its job as ``pending`` with the same ``result_course_id``
# (``generation_service.start_generation``), so including it would make a running
# content job masquerade as a schema job and hand its id back to a creator who asked
# for a schema. A schema job is inserted straight into ``schema_proposing``, so
# ``pending`` is unreachable for one. This tuple mirrors the ``WHERE`` of
# ``uq_generation_jobs_schema_in_flight`` in ``0005_dynamic_courses.py`` — they have
# to agree, or the read guard and the index disagree about what "in flight" means.
SCHEMA_JOB_IN_FLIGHT: tuple[GenerationStep, ...] = (GenerationStep.SCHEMA_PROPOSING,)


class GenerationJobRepository(BaseRepository[GenerationJob]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, GenerationJob)

    async def get_scoped(
        self, id: uuid.UUID, org_id: uuid.UUID
    ) -> GenerationJob | None:
        job = await self.get_by_id(id)
        if job is None or job.org_id != org_id:
            return None
        return job

    async def find_in_flight_schema_job(
        self, course_id: uuid.UUID, org_id: uuid.UUID
    ) -> GenerationJob | None:
        """The schema job already running for this course, if any.

        Oldest first, so concurrent callers converge on the same row instead of each
        seeing "the most recent one" and picking a different winner. Backed by the
        partial unique index ``uq_generation_jobs_schema_in_flight``
        (``0005_dynamic_courses.py``), which is what makes the guard hold when two
        requests race past this read.
        """
        query = (
            select(GenerationJob)
            .where(
                GenerationJob.result_course_id == course_id,
                GenerationJob.org_id == org_id,
                GenerationJob.status.in_(list(SCHEMA_JOB_IN_FLIGHT)),
                GenerationJob.cancelled_at.is_(None),
            )
            .order_by(GenerationJob.created_at.asc())
            .limit(1)
        )
        return (await self.session.execute(query)).scalar_one_or_none()
