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

import re
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import Response, StreamingResponse

from src.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from src.core.logging import get_logger
from src.core.sse import format_sse, subscribe
from src.deps.auth import CurrentUser
from src.deps.db import DBSession
from src.models import MediaKind, User, UserRole
from src.repositories.course_repo import CourseRepository
from src.repositories.learner_profile_repo import LearnerProfileRepository
from src.repositories.media_artifact_repo import MediaArtifactRepository
from src.schemas.media import (
    MediaArtifactAccepted,
    MediaArtifactCreate,
    MediaArtifactRead,
)
from src.services.artifact_access import can_generate_artifacts
from src.services.capabilities import derive_capabilities
from src.services.learner_memory import LearnerMemoryService
from src.services.media.assets import AssetStore
from src.services.media.jobs import enqueue_artifact, media_channel, spawn_media_job
from src.services.media.requirements import ensure_kind_is_available

logger = get_logger(__name__)

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


#: A content-hash sub-asset ref is a bare sha256 hex digest — anchored so no path segment,
#: separator or traversal can ever reach the asset store's ``path_for``.
_REF_RE = re.compile(r"^[0-9a-f]{64}$")


def _sub_assets(spec_json: dict | None) -> dict[str, str]:
    """Map each per-slide sub-asset's content-hash ref to its extension.

    The allow-list for :func:`get_artifact_sub_asset`: only refs this artifact's own spec
    lists are servable, so the route can never be coaxed into reading an unrelated file.
    Covers both the per-slide **audio** clip (``audio_ref``, mp3 by default) and the
    per-slide **illustration** (``image_ref``, png by default) — the Video Overview carries
    both, the slide deck carries only images. Additive — an artifact with neither yields
    ``{}``.
    """
    slides = (spec_json or {}).get("slides")
    if not isinstance(slides, list):
        return {}
    refs: dict[str, str] = {}
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        audio = slide.get("audio_ref")
        if isinstance(audio, str) and _REF_RE.match(audio):
            ext = slide.get("audio_ext")
            refs[audio] = ext if isinstance(ext, str) and ext else "mp3"
        image = slide.get("image_ref")
        if isinstance(image, str) and _REF_RE.match(image):
            ext = slide.get("image_ext")
            refs[image] = ext if isinstance(ext, str) and ext else "png"
    return refs


async def _remember_media_steering(
    db: DBSession, user: User, body: MediaArtifactCreate
) -> None:
    """Record the learner's steering note in their narrative memory (best-effort).

    This is the ONE writer that keeps a short slice of the user's own text verbatim: the
    "extra info" they typed to steer a generation is exactly the kind of preference the tutor
    and future generators should honour, so it is worth keeping literally (capped and
    curated by :class:`LearnerMemoryService`). See ``docs/learner-memory.md``.

    Employee-only (the memory is a learner concept), and never fatal: a failure here must not
    take down the ``202`` for a generation that is already enqueued and running.
    """
    if _role(user) != UserRole.EMPLOYEE.value:
        return
    spec = body.spec or {}
    steering = body.note or spec.get("prompt") or spec.get("steering")
    if not isinstance(steering, str) or not steering.strip():
        return
    kind = str(getattr(body.kind, "value", body.kind))
    try:
        service = LearnerMemoryService(LearnerProfileRepository(db))
        await service.note(
            user_id=user.id,
            org_id=user.org_id,
            section="Preferencias de contenido",
            text=f"Pidió enfoque: «{steering.strip()}» al generar {kind}",
            source="media",
        )
        await db.commit()
    except Exception as exc:  # noqa: BLE001 - the artifact is already enqueued
        logger.warning("Could not record media steering in learner memory: %s", exc)
        await db.rollback()


def _role(user: User) -> str:
    return str(getattr(user.role, "value", user.role))


@router.post("/artifacts", response_model=MediaArtifactAccepted, status_code=202)
async def create_artifact(
    user: CurrentUser, db: DBSession, body: MediaArtifactCreate
) -> MediaArtifactAccepted:
    """Enqueue one media generation job. Returns ``202 {artifact_id, status}``.

    The row is committed inside this request before the background task is spawned, so the
    task cannot race ahead of a row that does not exist yet (same order as node-render).

    A kind whose required capabilities are blocked is refused here with ``409
    capability_blocked`` rather than accepted: a job that cannot succeed must not be
    enqueued, run for half a minute and then show the user a provider's exception text.
    """
    course = await CourseRepository(db).get_scoped(body.course_id, user.org_id)
    if course is None:
        raise NotFoundError("courses", str(body.course_id))
    generator_ids = await CourseRepository(db).list_artifact_generator_ids(course.id)
    if not can_generate_artifacts(
        role=user.role,
        user_id=user.id,
        policy=getattr(course, "artifact_generate_policy", "admin"),
        generator_ids=generator_ids,
    ):
        raise ForbiddenError("You cannot generate overviews for this course")

    # ``MediaArtifactCreate`` is built with ``use_enum_values``, so ``kind`` arrives as the
    # plain string the client sent; the registry is keyed by the enum member.
    ensure_kind_is_available(MediaKind(str(body.kind)), derive_capabilities())

    node = None
    if body.node_id is not None:
        from src.repositories.course_node_repo import CourseNodeRepository

        node = await CourseNodeRepository(db).get_scoped(body.node_id, user.org_id)
        if node is None or node.course_id != course.id:
            raise ValidationError(
                "node_id does not belong to this course", field="node_id"
            )

    spec = dict(body.spec or {})
    scope = getattr(body.scope, "value", body.scope) or "node"
    spec["scope"] = scope
    # The personalization note is the learner's steering text. Keep the existing
    # ``prompt``/``steering`` keys authoritative if a client already set one; otherwise the
    # note becomes the steering the generators read.
    if body.note and body.note.strip():
        spec["note"] = body.note.strip()
        spec.setdefault("prompt", body.note.strip())
        # A standalone artefact is steered by the note: use it to focus grounding retrieval
        # too, so a node-less artefact still lands on the passages the learner asked about.
        if scope == "standalone":
            spec.setdefault("query", body.note.strip())

    artifact = await enqueue_artifact(
        db, course=course, node=node, kind=body.kind, spec=spec
    )
    await db.commit()

    await _remember_media_steering(db, user, body)

    spawn_media_job(artifact.id)
    return MediaArtifactAccepted(
        artifact_id=artifact.id,
        status=str(getattr(artifact.status, "value", artifact.status)),
    )


@router.get("/artifacts", response_model=list[MediaArtifactRead])
async def list_artifacts(
    user: CurrentUser,
    db: DBSession,
    course_id: uuid.UUID = Query(...),
    node_id: uuid.UUID | None = Query(default=None),
    include_nodes: bool = Query(default=False),
) -> list[MediaArtifactRead]:
    """Course overviews, one node's results, or everything for the course.

    Three shapes, all org-scoped:

    * ``node_id`` set -> only that node's artefacts.
    * ``include_nodes=true`` -> every artefact of the course (course-level *and*
      node-scoped), newest first, so the studio can list and manage the per-node podcasts
      and infographics the old course-only listing hid.
    * neither -> just the authored course-level overviews (the original default, so the
      course-home panel still never receives node-runtime audio/video).

    The static path cannot shadow ``/artifacts/{artifact_id}``.
    """
    course = await CourseRepository(db).get_scoped(course_id, user.org_id)
    if course is None:
        raise NotFoundError("courses", str(course_id))

    repository = MediaArtifactRepository(db)
    if node_id is not None:
        artifacts = await repository.list_for_course(
            course_id, user.org_id, node_id=node_id
        )
    elif include_nodes:
        artifacts = await repository.list_for_course(course_id, user.org_id)
    else:
        artifacts = await repository.list_course_level(course_id, user.org_id)
    return [MediaArtifactRead.of(artifact) for artifact in artifacts]


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


@router.get("/artifacts/{artifact_id}/asset/{ref}")
async def get_artifact_sub_asset(
    user: CurrentUser, db: DBSession, artifact_id: uuid.UUID, ref: str
) -> Response:
    """One named sub-asset of an artifact, addressed by content hash (``ref``).

    The Video Overview stores **one mp3 clip per slide** rather than a single rendered file
    (roadmap §2b: the frontend player sequences the slides, no ffmpeg). Each slide's
    ``audio_ref`` in ``spec_json`` is served here. ``ref`` must be a sha256 hex digest that
    the artifact's own spec lists — anything else is a ``404``, so the route can only ever
    serve clips this artifact produced. Additive and consistent with the single-asset route.
    """
    artifact = await MediaArtifactRepository(db).get_scoped(artifact_id, user.org_id)
    if artifact is None:
        raise NotFoundError("media_artifacts", str(artifact_id))

    allowed = _sub_assets(artifact.spec_json)
    ext = allowed.get(ref)
    if ext is None:
        raise NotFoundError("media_artifacts", str(artifact_id))

    store = AssetStore()
    path = store.path_for(ref, ext)
    try:
        data = store.read(path)
    except FileNotFoundError as exc:
        raise NotFoundError("media_artifacts", str(artifact_id)) from exc

    return Response(
        content=data,
        media_type=_MEDIA_TYPES.get(ext, "application/octet-stream"),
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )
