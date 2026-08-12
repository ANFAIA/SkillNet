"""Authenticated API for rich declarative activities."""

import uuid

from fastapi import APIRouter

from src.core.exceptions import NotFoundError, ValidationError
from src.deps.auth import AdminUser, CurrentUser
from src.deps.db import DBSession
from src.repositories.activity_definition_repo import (
    ActivityDefinitionRepository,
    ActivityStateRepository,
)
from src.repositories.course_node_repo import CourseNodeRepository
from src.repositories.course_repo import CourseRepository
from src.schemas.activity import (
    ActivityAction,
    ActivityDefinitionCreate,
    ActivityDefinitionRead,
    ActivityOperationRead,
    ActivityStateRead,
    ActivityStateWrite,
    ActivitySubmission,
)
from src.services.activity_definitions import ActivityDefinitionService, operation_payload

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
    return ActivityDefinitionRead.of(activity, missing_ports=service.missing_ports(activity))


@router.get("/{activity_id}/state", response_model=ActivityStateRead)
async def get_activity_state(user: CurrentUser, db: DBSession, activity_id: uuid.UUID) -> ActivityStateRead:
    service = _service(db)
    activity = await service.get(activity_id, user.org_id)
    row = await service.states.get_for_learner(activity.id, user.id)
    return ActivityStateRead.of(activity.id, row)


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
