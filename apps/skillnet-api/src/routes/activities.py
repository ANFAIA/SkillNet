"""Authenticated API for rich declarative activities."""

import uuid

from fastapi import APIRouter, Response

from src.core.exceptions import NotFoundError, ValidationError
from src.deps.auth import AdminUser, CurrentUser
from src.deps.db import DBSession
from src.repositories.activity_definition_repo import (
    ActivityDefinitionRepository,
    ActivityStateRepository,
)
from src.repositories.course_node_repo import CourseNodeRepository
from src.repositories.course_repo import CourseRepository
from src.repositories.learning_event_repo import LearningEventRepository
from src.schemas.activity import (
    ActivityAction,
    ActivityAssetRead,
    ActivityDefinitionCreate,
    ActivityDefinitionRead,
    ActivityProgressRead,
    DidactEventEnvelope,
    ActivityOperationRead,
    ActivityStateRead,
    ActivityStateWrite,
    ActivitySubmission,
)
from src.schemas.learning_experience import (
    ExperienceAttemptRead,
    ExperienceAttemptSubmission,
)
from src.services.activity_definitions import ActivityDefinitionService, operation_payload
from src.services.activity_ports import PortDeclined
from src.services.media.activity_assets import ActivityAssetResolver
from src.services.activity_progress import project_activity_progress
from src.services.experience_attempt_service import ExperienceAttemptService
from src.repositories.learner_node_state_repo import LearnerNodeStateRepository
from src.repositories.media_artifact_repo import MediaArtifactRepository

router = APIRouter(prefix="/activities", tags=["Activities"])


def _service(db: DBSession) -> ActivityDefinitionService:
    return ActivityDefinitionService(ActivityDefinitionRepository(db), ActivityStateRepository(db))


@router.post("", response_model=ActivityDefinitionRead, status_code=201)
async def create_activity(user: AdminUser, db: DBSession, body: ActivityDefinitionCreate) -> ActivityDefinitionRead:
    course = await CourseRepository(db).get_scoped(body.course_id, user.org_id)
    if course is None:
        raise NotFoundError("courses", str(body.course_id))
    node = await CourseNodeRepository(db).get_scoped(body.node_id, user.org_id)
    if node is None or node.course_id != course.id:
        raise ValidationError("node_id does not belong to course_id", field="node_id")
    service = _service(db)
    activity = await service.create(org_id=user.org_id, body=body)
    await db.commit()
    return ActivityDefinitionRead.of(activity, missing_ports=service.missing_ports(activity))


@router.get("/{activity_id}/definition", response_model=ActivityDefinitionRead)
async def get_activity_definition(user: CurrentUser, db: DBSession, activity_id: uuid.UUID) -> ActivityDefinitionRead:
    service = _service(db)
    activity = await service.get(activity_id, user.org_id)
    response = ActivityDefinitionRead.of(
        activity, missing_ports=service.missing_ports(activity)
    )
    if "assets" not in (activity.required_ports or []):
        return response
    asset_ref = (activity.public_definition or {}).get("assetRef")
    if not isinstance(asset_ref, str):
        return response.model_copy(
            update={"status": "declined", "decline_reason": "missing_asset_ref"}
        )
    resolved = await ActivityAssetResolver(MediaArtifactRepository(db)).resolve(
        activity, asset_ref
    )
    if isinstance(resolved, PortDeclined):
        return response.model_copy(
            update={"status": "declined", "decline_reason": resolved.reason}
        )
    if activity.component_id in {"didact.hotspot", "didact.label-diagram"}:
        if not resolved.mime_type.startswith("image/") or not resolved.width or not resolved.height:
            return response.model_copy(
                update={
                    "status": "declined",
                    "decline_reason": "spatial_asset_dimensions_required",
                }
            )
        key = "regions" if activity.component_id == "didact.hotspot" else "targets"
        spatial_ids = {
            str(item.get("id"))
            for item in (activity.public_definition or {}).get(key, [])
            if isinstance(item, dict) and item.get("id")
        }
        if not spatial_ids or not spatial_ids.issubset(resolved.verified_region_ids):
            return response.model_copy(
                update={
                    "status": "declined",
                    "decline_reason": "grounded_geometry_not_verified",
                }
            )
    if activity.component_id == "didact.interactive-media":
        definition = (activity.public_definition or {}).get("definition") or {}
        media = definition.get("media") if isinstance(definition, dict) else {}
        kind = media.get("kind") if isinstance(media, dict) else None
        authored_duration = media.get("durationMs") if isinstance(media, dict) else None
        if (
            resolved.duration_ms is None
            or authored_duration != resolved.duration_ms
            or resolved.duration_ms > 14_400_000
        ):
            return response.model_copy(
                update={
                    "status": "declined",
                    "decline_reason": "verified_media_duration_required",
                }
            )
        if kind == "audio" and not resolved.transcript:
            return response.model_copy(
                update={
                    "status": "declined",
                    "decline_reason": "audio_transcript_required",
                }
            )
        if kind == "video" and media.get("noSpeech") is not True and not resolved.captions:
            return response.model_copy(
                update={
                    "status": "declined",
                    "decline_reason": "video_captions_required",
                }
            )
    return response


@router.post("/{activity_id}/events", status_code=204)
async def record_activity_event(
    user: CurrentUser,
    db: DBSession,
    activity_id: uuid.UUID,
    body: DidactEventEnvelope,
) -> Response:
    """Record EventPort telemetry without changing mastery or ``format_vector``.

    A later node may consume only the bounded scored-evidence projection; the open
    render remains pinned and exposure/completion events stay inert.
    """
    activity = await _service(db).get(activity_id, user.org_id)
    if body.activity_id != activity.id:
        raise ValidationError("activity_id does not match the requested activity", field="activity_id")
    if body.component_id != activity.component_id:
        raise ValidationError("component_id does not match the activity definition", field="component_id")

    payload = body.payload.model_dump(mode="json", exclude_none=True)
    await LearningEventRepository(db).record_didact_event(
        event_id=body.event_id,
        user_id=user.id,
        node_id=activity.node_id,
        event_type=body.type,
        metadata={
            "schema_version": body.version,
            "activity_id": str(activity.id),
            "component_id": activity.component_id,
            "occurred_at": body.occurred_at.isoformat(),
            "payload": payload,
        },
    )
    await db.commit()
    return Response(status_code=204)


@router.get("/{activity_id}/state", response_model=ActivityStateRead)
async def get_activity_state(user: CurrentUser, db: DBSession, activity_id: uuid.UUID) -> ActivityStateRead:
    service = _service(db)
    activity = await service.get(activity_id, user.org_id)
    row = await service.states.get_for_learner(activity.id, user.id)
    return ActivityStateRead.of(activity.id, row)


@router.get("/{activity_id}/assets/{asset_ref}", response_model=ActivityAssetRead)
async def resolve_activity_asset(
    user: CurrentUser,
    db: DBSession,
    activity_id: uuid.UUID,
    asset_ref: str,
) -> ActivityAssetRead:
    """Resolve an opaque ref through the activity's server-owned scope."""
    activity = await _service(db).get(activity_id, user.org_id)
    resolved = await ActivityAssetResolver(MediaArtifactRepository(db)).resolve(
        activity, asset_ref
    )
    if isinstance(resolved, PortDeclined):
        raise NotFoundError("activity_assets", resolved.reason)
    return ActivityAssetRead(**resolved.as_payload())


@router.get("/{activity_id}/progress", response_model=ActivityProgressRead)
async def get_activity_progress(
    user: CurrentUser,
    db: DBSession,
    activity_id: uuid.UUID,
) -> ActivityProgressRead:
    """Read server-owned node mastery. Writes are intentionally absent."""
    activity = await _service(db).get(activity_id, user.org_id)
    row = await LearnerNodeStateRepository(db).get_by_user_and_node(user.id, activity.node_id)
    return ActivityProgressRead(**project_activity_progress(activity.component_id, row).as_payload())


@router.put("/{activity_id}/state", response_model=ActivityStateRead)
async def save_activity_state(user: CurrentUser, db: DBSession, activity_id: uuid.UUID, body: ActivityStateWrite) -> ActivityStateRead:
    service = _service(db)
    activity = await service.get(activity_id, user.org_id)
    row = await service.states.save(activity=activity, user_id=user.id, state=body.state)
    await db.commit()
    return ActivityStateRead.of(activity.id, row)


@router.post("/{activity_id}/evaluate", response_model=ActivityOperationRead)
async def evaluate_activity(user: CurrentUser, db: DBSession, activity_id: uuid.UUID, body: ActivitySubmission) -> ActivityOperationRead:
    service = _service(db)
    activity = await service.get(activity_id, user.org_id)
    return ActivityOperationRead(**operation_payload(await service.evaluate(activity, body.submission)))


@router.post("/{activity_id}/attempts", response_model=ExperienceAttemptRead)
async def submit_experience_attempt(
    user: CurrentUser,
    db: DBSession,
    activity_id: uuid.UUID,
    body: ExperienceAttemptSubmission,
) -> ExperienceAttemptRead:
    """Evaluate once and atomically persist neutral evidence plus mastery.

    The client supplies identity, binding, raw submission and duration only. Scoring,
    evidence normalization and all learner-state changes remain server-owned.
    """

    result = await ExperienceAttemptService(db).submit(
        user=user, activity_id=activity_id, body=body
    )
    await db.commit()
    return result


@router.post("/{activity_id}/transition", response_model=ActivityOperationRead)
async def transition_activity(user: CurrentUser, db: DBSession, activity_id: uuid.UUID, body: ActivityAction) -> ActivityOperationRead:
    service = _service(db)
    activity = await service.get(activity_id, user.org_id)
    return ActivityOperationRead(**operation_payload(await service.transition(activity, body.state, body.action)))


@router.post("/{activity_id}/execute", response_model=ActivityOperationRead)
async def execute_activity(user: CurrentUser, db: DBSession, activity_id: uuid.UUID, body: ActivitySubmission) -> ActivityOperationRead:
    service = _service(db)
    activity = await service.get(activity_id, user.org_id)
    return ActivityOperationRead(**operation_payload(await service.execute(activity, body.submission)))
