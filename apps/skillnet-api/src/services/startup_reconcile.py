"""Fail whatever a previous process left running, once, at startup.

Every background job in this API is an ``asyncio.Task`` inside one uvicorn worker
(``src/core/tasks.py``, and the image runs ``--workers 1``). Tasks do not survive the
process. Nothing used to notice: a redeploy, a crash or a ``docker compose restart`` in
the middle of a generation left

* ``generation_jobs`` sitting in ``pending`` / ``schema_proposing`` / ``generating`` …
  forever — and a ``schema_proposing`` row is worse than cosmetic, because
  ``GenerationJobRepository.find_in_flight_schema_job`` treats it as a run in flight and
  **permanently refuses** ``POST /courses/{id}/schema/propose`` for that course;
* ``node_knowledge_packs`` sitting in ``pending`` forever, which is the state the course
  finalization run waits on;
* ``courses.generation_state`` sitting in ``in_progress`` forever (migration 0025).

None of those rows can ever move again on their own, because the only thing that would
have moved them died with the process. Marking them failed with a reason that says so is
the difference between "this deployment restarted, press retry" and a deadlock nobody
can diagnose from the UI.

Safe to run unconditionally *because* the worker count is one: at the moment this runs,
no task from this process exists yet, and any task from another process cannot exist.
If the deployment ever grows a second worker this has to become a lease, not a sweep.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.models import (
    Course,
    CourseGenerationState,
    GenerationJob,
    GenerationStep,
    NodeKnowledgePackRecord,
    NodeKnowledgePackStatus,
)
from src.services.course_finalization import ERROR_INTERRUPTED, ERROR_MESSAGES

logger = get_logger(__name__)

#: Everything a generation job can be in while it is still being worked on. The terminal
#: states — ``schema_proposed``, ``published``, ``failed`` — are deliberately absent.
_UNFINISHED_JOB_STATES = (
    GenerationStep.PENDING,
    GenerationStep.SCHEMA_PROPOSING,
    GenerationStep.EXTRACTING,
    GenerationStep.STRUCTURING,
    GenerationStep.GENERATING,
    GenerationStep.REVIEWING,
)

#: What the swept rows say happened. English, short, and true.
INTERRUPTED_MESSAGE = "Interrupted: the server restarted while this was running."


@dataclass(frozen=True)
class ReconcileReport:
    """How much of the previous process's work had to be written off."""

    jobs: int
    knowledge_packs: int
    courses: int

    @property
    def total(self) -> int:
        return self.jobs + self.knowledge_packs + self.courses


async def reconcile_interrupted_work(session: AsyncSession) -> ReconcileReport:
    """Mark every non-terminal row from a dead process failed. Commits."""
    now = datetime.now(timezone.utc)

    jobs = await session.execute(
        update(GenerationJob)
        .where(
            GenerationJob.status.in_(_UNFINISHED_JOB_STATES),
            GenerationJob.cancelled_at.is_(None),
        )
        .values(
            status=GenerationStep.FAILED,
            error_message=INTERRUPTED_MESSAGE,
            cancelled_at=now,
        )
    )

    packs = await session.execute(
        update(NodeKnowledgePackRecord)
        .where(NodeKnowledgePackRecord.status == NodeKnowledgePackStatus.PENDING)
        .values(
            status=NodeKnowledgePackStatus.FAILED,
            error_message=INTERRUPTED_MESSAGE,
        )
    )

    courses = await session.execute(
        update(Course)
        .where(Course.generation_state == CourseGenerationState.IN_PROGRESS)
        .values(
            generation_state=CourseGenerationState.FAILED,
            generation_error=ERROR_MESSAGES[ERROR_INTERRUPTED],
            generation_failed_at=now,
        )
    )

    await session.commit()
    report = ReconcileReport(
        jobs=int(jobs.rowcount or 0),
        knowledge_packs=int(packs.rowcount or 0),
        courses=int(courses.rowcount or 0),
    )
    if report.total:
        logger.warning(
            "Startup reconcile: failed %s generation job(s), %s knowledge pack(s), "
            "%s course(s) left running by a previous process",
            report.jobs,
            report.knowledge_packs,
            report.courses,
        )
    return report


__all__ = ["INTERRUPTED_MESSAGE", "ReconcileReport", "reconcile_interrupted_work"]
