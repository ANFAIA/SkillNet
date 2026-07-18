"""Generation job routes: status fetch and SSE progress stream."""

import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.core.exceptions import NotFoundError
from src.core.sse import format_sse, subscribe
from src.deps.auth import AdminUser
from src.deps.db import DBSession
from src.repositories.generation_job_repo import GenerationJobRepository
from src.schemas.generation_job import GenerationJobRead

router = APIRouter(prefix="/generation-jobs", tags=["Generation Jobs"])

_TERMINAL_EVENTS = {"completed", "error"}


@router.get("/{job_id}", response_model=GenerationJobRead)
async def get_job(
    admin: AdminUser, db: DBSession, job_id: uuid.UUID
) -> GenerationJobRead:
    repo = GenerationJobRepository(db)
    job = await repo.get_scoped(job_id, admin.org_id)
    if job is None:
        raise NotFoundError("generation_jobs", str(job_id))
    return GenerationJobRead.model_validate(job)


@router.get("/{job_id}/progress")
async def stream_progress(
    admin: AdminUser, db: DBSession, job_id: uuid.UUID
) -> StreamingResponse:
    repo = GenerationJobRepository(db)
    job = await repo.get_scoped(job_id, admin.org_id)
    if job is None:
        raise NotFoundError("generation_jobs", str(job_id))

    async def event_stream() -> AsyncIterator[str]:
        async for event in subscribe(f"generation:{job_id}"):
            yield format_sse(event["type"], event["data"])
            if event["type"] in _TERMINAL_EVENTS:
                break

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
