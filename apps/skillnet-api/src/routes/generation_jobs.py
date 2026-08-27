"""Generation job routes: status fetch and SSE progress stream."""

import asyncio
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.core.exceptions import NotFoundError
from src.core.sse import Subscription, format_sse
from src.deps.auth import AdminUser
from src.deps.db import DBSession, async_session_factory
from src.models import GenerationStep
from src.repositories.generation_job_repo import GenerationJobRepository
from src.schemas.generation_job import GenerationJobRead

router = APIRouter(prefix="/generation-jobs", tags=["Generation Jobs"])

_TERMINAL_EVENTS = {"completed", "error", "schema_ready"}

#: How long the stream may stay silent before it sends a comment frame. ``docker/
#: nginx.conf`` closes an idle proxied stream at ``proxy_read_timeout 300s``, and a
#: generation step can easily take longer than that, so without a heartbeat the proxy
#: kills a stream that is working perfectly and the browser is left with a spinner.
KEEPALIVE_SECONDS = 20.0

#: An SSE comment. Keeps the connection warm without inventing an event the client
#: would have to know how to ignore.
_KEEPALIVE_FRAME = ": keepalive\n\n"


@router.get("/{job_id}", response_model=GenerationJobRead)
async def get_job(
    admin: AdminUser, db: DBSession, job_id: uuid.UUID
) -> GenerationJobRead:
    repo = GenerationJobRepository(db)
    job = await repo.get_scoped(job_id, admin.org_id)
    if job is None:
        raise NotFoundError("generation_jobs", str(job_id))
    return GenerationJobRead.model_validate(job)


def _replay(status: GenerationStep, course_id: uuid.UUID | None, error: str | None):
    """The job's current state as one event, for a client that has just connected.

    ``src/core/sse.py`` fans out to whoever is subscribed *at publish time* and keeps no
    backlog, and this route never called ``wait_for_subscriber``. So a client that opened
    the stream a moment after the worker published — a reload, a retry, a slow first
    paint — used to see nothing at all and sit on "pending" until the job finished, or
    forever if it had already finished before the connection opened.
    """
    if status is GenerationStep.PUBLISHED:
        return "completed", {"course_id": str(course_id) if course_id else None}
    if status is GenerationStep.FAILED:
        return "error", {"message": error or "Generation failed"}
    if status is GenerationStep.SCHEMA_PROPOSED:
        return "schema_ready", {"course_id": str(course_id) if course_id else None}
    return "step", {"step": status.value}


@router.get("/{job_id}/progress")
async def stream_progress(
    admin: AdminUser, db: DBSession, job_id: uuid.UUID
) -> StreamingResponse:
    repo = GenerationJobRepository(db)
    job = await repo.get_scoped(job_id, admin.org_id)
    if job is None:
        raise NotFoundError("generation_jobs", str(job_id))
    org_id = admin.org_id

    async def event_stream() -> AsyncIterator[str]:
        # Registered *before* the status is read, so an event published while the row is
        # being read is queued rather than lost in the gap between the two. This is why
        # it is a `Subscription` and not `subscribe()`: the generator form registers
        # nothing until its first await, which would put the read inside that gap.
        subscription = Subscription(f"generation:{job_id}")
        try:
            async with async_session_factory() as session:
                current = await GenerationJobRepository(session).get_scoped(
                    job_id, org_id
                )
            if current is not None:
                event_type, data = _replay(
                    current.status, current.result_course_id, current.error_message
                )
                yield format_sse(event_type, data)
                if event_type in _TERMINAL_EVENTS:
                    return

            while True:
                try:
                    event = await asyncio.wait_for(
                        subscription.get(), timeout=KEEPALIVE_SECONDS
                    )
                except asyncio.TimeoutError:
                    yield _KEEPALIVE_FRAME
                    continue
                yield format_sse(event["type"], event["data"])
                if event["type"] in _TERMINAL_EVENTS:
                    return
        finally:
            subscription.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
