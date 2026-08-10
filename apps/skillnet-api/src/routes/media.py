"""Rich-media artifact surface: enqueue a job, poll/stream its status, fetch its asset.

Minimal and strictly additive — it introduces its own ``/media`` prefix and touches no
existing route. The three verbs mirror the node-render contract so the frontend reuses the
same background-job UX (TanStack ``refetchInterval`` while ``pending|running``, or the SSE
stream): ``202`` on enqueue, ``GET`` for the row, ``GET .../stream`` for SSE progress, and
``GET .../asset`` for the rendered bytes.

Everything is org-scoped through :meth:`MediaArtifactRepository.get_scoped`: a media
artifact is shared by the whole organization (like ``node_renders``), so authorization is
"the artifact belongs to your org", not per-user ownership.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import Response, StreamingResponse

from src.core.exceptions import NotFoundError, ValidationError
from src.core.sse import format_sse, subscribe
from src.deps.auth import CurrentUser
from src.deps.db import DBSession
from src.repositories.course_repo import CourseRepository
from src.repositories.media_artifact_repo import MediaArtifactRepository
from src.schemas.media import (
    MediaArtifactAccepted,
    MediaArtifactCreate,
    MediaArtifactRead,
)
from src.services.media.assets import AssetStore
from src.services.media.jobs import enqueue_artifact, media_channel, spawn_media_job

router = APIRouter(prefix="/media", tags=["Media"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}

#: Events after which a media job's stream has nothing left to say.
_TERMINAL_EVENTS = {"media_done", "media_error"}

#: File extension -> HTTP media type for the asset route.
_MEDIA_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "mp3": "audio/mpeg",
    "mp4": "video/mp4",
    "svg": "image/svg+xml",
    "json": "application/json",
}


def _media_type(asset_path: str) -> str:
    ext = Path(asset_path).suffix.lstrip(".").lower()
    return _MEDIA_TYPES.get(ext, "application/octet-stream")


@router.post("/artifacts", response_model=MediaArtifactAccepted, status_code=202)
async def create_artifact(
    user: CurrentUser, db: DBSession, body: MediaArtifactCreate
) -> MediaArtifactAccepted:
    """Enqueue one media generation job. Returns ``202 {artifact_id, status}``.

    The row is committed inside this request before the background task is spawned, so the
    task cannot race ahead of a row that does not exist yet (same order as node-render).
    """
    course = await CourseRepository(db).get_scoped(body.course_id, user.org_id)
    if course is None:
        raise NotFoundError("courses", str(body.course_id))

    node = None
    if body.node_id is not None:
        from src.repositories.course_node_repo import CourseNodeRepository

        node = await CourseNodeRepository(db).get_scoped(body.node_id, user.org_id)
        if node is None or node.course_id != course.id:
            raise ValidationError(
                "node_id does not belong to this course", field="node_id"
            )

    artifact = await enqueue_artifact(
        db, course=course, node=node, kind=body.kind, spec=body.spec
    )
    await db.commit()

    spawn_media_job(artifact.id)
    return MediaArtifactAccepted(
        artifact_id=artifact.id,
        status=str(getattr(artifact.status, "value", artifact.status)),
    )


@router.get("/artifacts/{artifact_id}", response_model=MediaArtifactRead)
async def get_artifact(
    user: CurrentUser, db: DBSession, artifact_id: uuid.UUID
) -> MediaArtifactRead:
    """The artifact row: status, grounded spec, whether an asset is ready."""
    artifact = await MediaArtifactRepository(db).get_scoped(artifact_id, user.org_id)
    if artifact is None:
        raise NotFoundError("media_artifacts", str(artifact_id))
    return MediaArtifactRead.of(artifact)


@router.get("/artifacts/{artifact_id}/stream")
async def stream_artifact(
    user: CurrentUser,
    db: DBSession,
    artifact_id: uuid.UUID,
    request_id: str = Query(default=""),  # noqa: ARG001 - reserved for symmetry with nodes
) -> StreamingResponse:
    """SSE for one media job. Channel ``media:{artifact_id}``.

    Events: ``media_step`` (running, grounded), then one terminal ``media_done`` /
    ``media_error``. The stream closes on the first terminal event.
    """
    artifact = await MediaArtifactRepository(db).get_scoped(artifact_id, user.org_id)
    if artifact is None:
        raise NotFoundError("media_artifacts", str(artifact_id))
    channel = media_channel(artifact_id)

    async def event_stream() -> AsyncIterator[str]:
        async for event in subscribe(channel):
            yield format_sse(event["type"], event["data"])
            if event["type"] in _TERMINAL_EVENTS:
                break

    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=_SSE_HEADERS
    )


@router.get("/artifacts/{artifact_id}/asset")
async def get_artifact_asset(
    user: CurrentUser, db: DBSession, artifact_id: uuid.UUID
) -> Response:
    """The rendered bytes (mp3/png/mp4/...), or ``404`` if there is nothing to serve."""
    artifact = await MediaArtifactRepository(db).get_scoped(artifact_id, user.org_id)
    if artifact is None or not artifact.asset_path:
        raise NotFoundError("media_artifacts", str(artifact_id))

    try:
        data = AssetStore().read(artifact.asset_path)
    except FileNotFoundError as exc:
        # The row points at an asset that is no longer on disk — a 404 the client can
        # handle by re-requesting generation, not a 500.
        raise NotFoundError("media_artifacts", str(artifact_id)) from exc

    return Response(
        content=data,
        media_type=_media_type(artifact.asset_path),
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )
