"""Finish creating a v2 course on the server, not in the creator's browser tab.

Creating a dynamic course used to end with three round trips driven from
``pages/admin/CreateCourse.tsx``: poll until every node's knowledge pack is ready, mark
the graph reviewed, validate it. Only the last of those publishes the course
(``CourseSchemaService.validate``), so a tab that stopped executing anywhere in that
window — closed, reloaded, backgrounded and killed, network dropped, API redeployed —
left the row as a permanent draft with nothing recording that a run had died. Pressing
"create" again started from scratch and produced a *second* course.

This module is that tail of the wizard, moved behind one 202 endpoint:

    claim (``generation_state = in_progress``, in the request's transaction)
      -> wait for the knowledge packs
      -> review every node
      -> validate, which is what publishes the course
      -> ``generation_state = complete``

Every exit writes a terminal ``generation_state``, so "still creating" and "creation
died" are finally different states in the database instead of both being ``draft``. The
browser's job shrinks to: create, PUT the schema, call this, watch.

The failure text is short, safe and English, and never the exception — the discipline
``src/services/media/jobs.classify_failure`` established: a provider's raw exception is
unreadable at best and leaks endpoints, model names or account identifiers at worst.
The operator keeps the whole traceback in the log.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from src.core.exceptions import LLMError
from src.core.logging import get_logger
from src.core.tasks import task_registry
from src.deps.db import async_session_factory
from src.models import (
    Course,
    CourseGenerationState,
    NodeKnowledgePackStatus,
)
from src.repositories.audit_log_repo import AuditLogRepository
from src.repositories.course_node_repo import CourseNodeRepository
from src.repositories.course_repo import CourseRepository
from src.repositories.document_repo import DocumentRepository
from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.generation_job_repo import GenerationJobRepository
from src.repositories.node_knowledge_pack_repo import NodeKnowledgePackRepository
from src.services import provider_health
from src.services.course_schema_service import CourseSchemaService, SchemaError
from src.services.node_render_service import spawn_prewarm_first_nodes

logger = get_logger(__name__)

#: Task name prefix, so a second call for the same course adopts the running task
#: instead of starting a rival one (:meth:`TaskRegistry.spawn_unique`).
TASK_PREFIX = "finalize-course:"

#: How long the run waits for every node's knowledge pack to leave ``pending``, and how
#: often it looks. The ceiling matches the browser poll this replaces (300 s) — a stuck
#: pack must not pin the run open forever, and validating anyway still yields a usable
#: course whose slow nodes fall back to the preparing shell.
PACK_WAIT_SECONDS = 300.0
PACK_POLL_SECONDS = 2.0

#: Stable failure codes. ``generation_error`` carries the sentence beside them; the code
#: is what a caller should branch on if it ever needs to.
ERROR_LLM_FAILED = "llm_failed"
ERROR_PROVIDER_QUOTA = "provider_quota"
ERROR_PROVIDER_DOWN = "provider_down"
ERROR_SCHEMA_REJECTED = "schema_rejected"
ERROR_CANCELLED = "cancelled"
ERROR_INTERRUPTED = "interrupted"
ERROR_INTERNAL = "internal_error"

ERROR_MESSAGES: dict[str, str] = {
    ERROR_LLM_FAILED: "The AI provider could not finish preparing this course.",
    ERROR_PROVIDER_QUOTA: "The provider is out of quota. Try again later.",
    ERROR_PROVIDER_DOWN: "The provider is unavailable right now. Try again later.",
    ERROR_SCHEMA_REJECTED: "The schema was rejected. Review the nodes and try again.",
    ERROR_CANCELLED: "Course creation was cancelled.",
    ERROR_INTERRUPTED: "The server restarted while this course was being created.",
    ERROR_INTERNAL: "Course creation failed. The details are in the server log.",
}

#: Mirrors ``courses.generation_error``'s column width (migration 0025).
_ERROR_CHARS = 500


def classify_failure(exc: BaseException) -> tuple[str, str]:
    """Map an exception to ``(error_code, safe message)``. Never leaks exception text."""
    if isinstance(exc, SchemaError):
        return ERROR_SCHEMA_REJECTED, ERROR_MESSAGES[ERROR_SCHEMA_REJECTED]
    kind = provider_health.failure_kind(exc)
    if kind == "quota":
        return ERROR_PROVIDER_QUOTA, ERROR_MESSAGES[ERROR_PROVIDER_QUOTA]
    if isinstance(exc, LLMError):
        return ERROR_LLM_FAILED, ERROR_MESSAGES[ERROR_LLM_FAILED]
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return ERROR_PROVIDER_DOWN, ERROR_MESSAGES[ERROR_PROVIDER_DOWN]
    return ERROR_INTERNAL, ERROR_MESSAGES[ERROR_INTERNAL]


@dataclass(frozen=True)
class FinalizationStatus:
    """What the wizard needs on every poll, in one read."""

    course_id: uuid.UUID
    generation_state: str
    generation_error: str | None
    generation_failed_at: datetime | None
    schema_status: str
    status: str
    packs_ready: int
    packs_total: int


def _service(db) -> CourseSchemaService:
    return CourseSchemaService(
        CourseRepository(db),
        CourseNodeRepository(db),
        AuditLogRepository(db),
        EnrollmentRepository(db),
        GenerationJobRepository(db),
        DocumentRepository(db),
    )


async def read_status(db, *, course: Course) -> FinalizationStatus:
    """Project one course's creation-run state plus its knowledge-pack progress.

    The pack counts are the honest progress bar the wizard needs: "3 of 8 ready" instead
    of five checkmarks that advance on a timer regardless of what the server is doing.
    """
    nodes = list(
        await CourseNodeRepository(db).list_for_course(course.id, include_archived=False)
    )
    schema_version = int(course.schema_version or 1)
    rows = await NodeKnowledgePackRepository(db).latest_for_schema(
        course_id=course.id, org_id=course.org_id, schema_version=schema_version
    )
    node_ids = {node.id for node in nodes}
    ready = sum(
        1
        for row in rows
        if row.node_id in node_ids and row.status is not NodeKnowledgePackStatus.PENDING
    )
    return FinalizationStatus(
        course_id=course.id,
        generation_state=course.generation_state.value,
        generation_error=course.generation_error,
        generation_failed_at=course.generation_failed_at,
        schema_status=course.schema_status.value,
        status=course.status.value,
        packs_ready=ready,
        packs_total=len(nodes),
    )


def claim(course: Course) -> None:
    """Mark the course as owned by a creation run. The caller commits.

    Claiming inside the request's transaction is what makes the retry safe: the row is
    already ``in_progress`` before the 202 is written, so a reload that lands on the
    wizard sees the run rather than a draft it would be tempted to re-create.
    """
    course.generation_state = CourseGenerationState.IN_PROGRESS
    course.generation_error = None
    course.generation_failed_at = None


def spawn(course_id: uuid.UUID, org_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    """Schedule :func:`run` after the claim has been committed.

    ``spawn_unique`` on a per-course name, so pressing "create" twice adopts the run in
    flight instead of racing a second one through review and validate.
    """
    coroutine = run(course_id, org_id, actor_id)
    try:
        task_registry.spawn_unique(coroutine, name=f"{TASK_PREFIX}{course_id}")
        return
    except Exception:  # noqa: BLE001 - report the failure on the row, not by crashing
        coroutine.close()
        logger.warning(
            "Could not schedule course finalization course=%s", course_id, exc_info=True
        )

    # The row is already claimed as ``in_progress`` and nothing will move it, so the
    # failure has to be written or the course is stranded exactly as before.
    failure = _record_failure(course_id, org_id, ERROR_INTERNAL)
    try:
        task_registry.spawn(failure, name=f"{TASK_PREFIX}{course_id}:failed")
    except Exception:  # noqa: BLE001 - nothing left to try; do not leak the coroutine
        failure.close()
        logger.error(
            "Could not record an unschedulable finalization course=%s",
            course_id,
            exc_info=True,
        )


async def run(course_id: uuid.UUID, org_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    """Wait for the packs, review the graph, validate it, record the outcome."""
    try:
        waited = await _wait_for_packs(course_id, org_id)
        if not waited:
            # Not fatal, and deliberately so: the browser poll this replaces also gave
            # up at the ceiling and validated anyway. A course with a slow pack is
            # usable — its node shows the preparing shell until the pack lands.
            logger.warning(
                "Knowledge packs still pending at the ceiling; validating anyway "
                "course=%s",
                course_id,
            )
        await _review_and_validate(course_id, org_id, actor_id)
    except asyncio.CancelledError:
        await _record_failure(course_id, org_id, ERROR_CANCELLED)
        raise
    except Exception as exc:  # noqa: BLE001 - every exit writes a terminal state
        code, _ = classify_failure(exc)
        logger.error(
            "Course finalization failed course=%s code=%s", course_id, code, exc_info=True
        )
        await _record_failure(course_id, org_id, code)


async def _wait_for_packs(course_id: uuid.UUID, org_id: uuid.UUID) -> bool:
    """Block until every node has a non-``pending`` pack. ``False`` if the ceiling won.

    A node becomes a real episode only once its pack leaves ``pending``; validating and
    pre-rendering before that pins the flat fallback screen for the first learner.
    """
    deadline = asyncio.get_running_loop().time() + PACK_WAIT_SECONDS
    while True:
        async with async_session_factory() as db:
            course = await CourseRepository(db).get_scoped(course_id, org_id)
            if course is None:
                raise LookupError(f"course {course_id} disappeared while creating it")
            status = await read_status(db, course=course)
        if status.packs_total == 0 or status.packs_ready >= status.packs_total:
            return True
        if asyncio.get_running_loop().time() >= deadline:
            return False
        await asyncio.sleep(PACK_POLL_SECONDS)


async def _review_and_validate(
    course_id: uuid.UUID, org_id: uuid.UUID, actor_id: uuid.UUID
) -> None:
    """The two calls that finish a course, plus the state write that records it."""
    async with async_session_factory() as db:
        service = _service(db)
        snapshot = await service.get_schema(course_id=course_id, org_id=org_id)
        for node in snapshot.nodes:
            if node.reviewed_at is None and not node.archived:
                await service.mark_reviewed(
                    course_id=course_id,
                    org_id=org_id,
                    node_id=node.id,
                    actor_id=actor_id,
                )
        await db.commit()

    async with async_session_factory() as db:
        service = _service(db)
        snapshot = await service.validate(
            course_id=course_id, org_id=org_id, actor_id=actor_id
        )
        course = snapshot.course
        course.generation_state = CourseGenerationState.COMPLETE
        course.generation_error = None
        course.generation_failed_at = None
        schema_version = int(course.schema_version or 1)
        await db.commit()

    # Same warm-up the ``validate`` route does: the course is servable now, but no node
    # render exists yet, so the first learner would pay the full generation latency.
    spawn_prewarm_first_nodes(course_id, org_id, schema_version, actor_id)


async def _record_failure(
    course_id: uuid.UUID, org_id: uuid.UUID, code: str
) -> None:
    """Write the terminal ``failed`` state and its safe reason. Never raises."""
    message = ERROR_MESSAGES.get(code, ERROR_MESSAGES[ERROR_INTERNAL])
    try:
        async with async_session_factory() as db:
            course = await CourseRepository(db).get_scoped(course_id, org_id)
            if course is None:
                return
            course.generation_state = CourseGenerationState.FAILED
            course.generation_error = message[:_ERROR_CHARS]
            course.generation_failed_at = datetime.now(timezone.utc)
            await db.commit()
    except Exception:  # noqa: BLE001 - the run already failed; do not fail the failure
        logger.error(
            "Could not record finalization failure course=%s", course_id, exc_info=True
        )


__all__ = [
    "ERROR_MESSAGES",
    "PACK_POLL_SECONDS",
    "PACK_WAIT_SECONDS",
    "TASK_PREFIX",
    "FinalizationStatus",
    "claim",
    "classify_failure",
    "read_status",
    "run",
    "spawn",
]
