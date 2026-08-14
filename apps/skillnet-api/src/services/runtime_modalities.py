"""On-demand delivery modalities for one learning node.

These outputs are runtime representations, not authored course content. The media spine is
used only as an asynchronous persistence/cache mechanism; callers never inspect the course
overview library to decide what a learner may open.
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Course, CourseNode, MediaArtifact, MediaArtifactStatus, MediaKind
from src.repositories.media_artifact_repo import MediaArtifactRepository
from src.services.media.jobs import enqueue_artifact, spawn_media_job

RuntimeModality = Literal["audio", "video"]

_KINDS: dict[RuntimeModality, MediaKind] = {
    "audio": MediaKind.PODCAST,
    "video": MediaKind.VIDEO,
}
_REUSABLE = {
    MediaArtifactStatus.PENDING,
    MediaArtifactStatus.RUNNING,
    MediaArtifactStatus.DONE,
}


async def request_runtime_modality(
    db: AsyncSession,
    *,
    course: Course,
    node: CourseNode,
    modality: RuntimeModality,
    language: str = "es",
) -> tuple[MediaArtifact, bool]:
    """Return the current node representation or enqueue it on first activation.

    A ready or in-flight result is reused so reloads and repeated clicks do not start new
    jobs. Failed generations are not sticky: a later request creates a fresh attempt.
    """
    kind = _KINDS[modality]
    existing = await MediaArtifactRepository(db).list_for_course(
        course.id, course.org_id, node_id=node.id
    )
    reusable = next(
        (
            item
            for item in existing
            if item.kind == kind and item.status in _REUSABLE
        ),
        None,
    )
    if reusable is not None:
        return reusable, False

    artifact = await enqueue_artifact(
        db,
        course=course,
        node=node,
        kind=kind,
        spec={
            "language": language if language in {"es", "en"} else "es",
            "delivery_scope": "runtime_node",
        },
    )
    await db.commit()
    spawn_media_job(artifact.id)
    return artifact, True


__all__ = ["RuntimeModality", "request_runtime_modality"]
