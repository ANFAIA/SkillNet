"""Enrollment routes: list, assign, detail with progress, and removal."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from src.core.exceptions import ForbiddenError, ValidationError
from src.deps.auth import AdminUser, CurrentUser
from src.deps.db import DBSession
from src.models import Enrollment, EnrollmentStatus, UserRole
from src.repositories.course_repo import CourseRepository
from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.exercise_repo import ExerciseRepository
from src.schemas.common import PaginatedResponse
from src.schemas.enrollment import EnrollmentCreate, EnrollmentRead
from src.services.course_delivery import resolve_delivery
from src.services.enrollment_service import EnrollmentService

router = APIRouter(prefix="/enrollments", tags=["Enrollments"])


def _service(db: DBSession) -> EnrollmentService:
    return EnrollmentService(
        EnrollmentRepository(db), CourseRepository(db), ExerciseRepository(db)
    )


def _parse_status(status: str | None) -> EnrollmentStatus | None:
    if status is None:
        return None
    try:
        return EnrollmentStatus(status)
    except ValueError as exc:
        raise ValidationError(f"Invalid status: {status}", field="status") from exc


def _read(enrollment: Enrollment, progress: float | None) -> EnrollmentRead:
    course_title = enrollment.course.title if enrollment.course else None
    delivery_mode = (
        resolve_delivery(enrollment.course) if enrollment.course else "static"
    )
    return EnrollmentRead(
        id=enrollment.id,
        course_id=enrollment.course_id,
        user_id=enrollment.user_id,
        status=enrollment.status.value,
        deadline=enrollment.deadline,
        score=enrollment.score,
        progress=progress,
        course_title=course_title,
        started_at=enrollment.started_at,
        completed_at=enrollment.completed_at,
        delivery_mode=delivery_mode,
    )


@router.get("", response_model=PaginatedResponse[EnrollmentRead])
async def list_enrollments(
    user: CurrentUser,
    db: DBSession,
    status: Annotated[str | None, Query()] = None,
    user_id: Annotated[uuid.UUID | None, Query()] = None,
    course_id: Annotated[uuid.UUID | None, Query()] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PaginatedResponse[EnrollmentRead]:
    service = _service(db)
    # Employees only ever see their own enrollments.
    effective_user_id = user.id if user.role == UserRole.EMPLOYEE else user_id
    rows, total = await service.list_enrollments(
        org_id=user.org_id,
        user_id=effective_user_id,
        course_id=course_id,
        status=_parse_status(status),
        offset=offset,
        limit=limit,
    )
    items = []
    for enrollment in rows:
        progress = await service.compute_progress(
            enrollment=enrollment, org_id=user.org_id
        )
        items.append(_read(enrollment, progress))
    return PaginatedResponse[EnrollmentRead](
        items=items, total=total, offset=offset, limit=limit
    )


@router.post("", response_model=list[EnrollmentRead], status_code=201)
async def create_enrollments(
    admin: AdminUser, db: DBSession, body: EnrollmentCreate
) -> list[EnrollmentRead]:
    service = _service(db)
    created = await service.assign(
        org_id=admin.org_id,
        assigned_by=admin.id,
        course_id=body.course_id,
        user_ids=body.user_ids,
        deadline=body.deadline,
    )
    await db.commit()
    result = []
    for enrollment in created:
        loaded = await service.get_scoped(
            enrollment_id=enrollment.id, org_id=admin.org_id
        )
        result.append(_read(loaded, 0.0))
    return result


@router.get("/{enrollment_id}", response_model=EnrollmentRead)
async def get_enrollment(
    user: CurrentUser, db: DBSession, enrollment_id: uuid.UUID
) -> EnrollmentRead:
    service = _service(db)
    enrollment = await service.get_scoped(
        enrollment_id=enrollment_id, org_id=user.org_id
    )
    if user.role == UserRole.EMPLOYEE and enrollment.user_id != user.id:
        raise ForbiddenError("You can only view your own enrollments")
    progress = await service.compute_progress(
        enrollment=enrollment, org_id=user.org_id
    )
    return _read(enrollment, progress)


@router.post("/{enrollment_id}/complete", response_model=EnrollmentRead)
async def complete_enrollment(
    user: CurrentUser, db: DBSession, enrollment_id: uuid.UUID
) -> EnrollmentRead:
    service = _service(db)
    enrollment, progress = await service.complete(
        enrollment_id=enrollment_id, org_id=user.org_id, user_id=user.id
    )
    await db.commit()
    return _read(enrollment, progress)


@router.delete("/{enrollment_id}", status_code=204)
async def delete_enrollment(
    admin: AdminUser, db: DBSession, enrollment_id: uuid.UUID
) -> Response:
    service = _service(db)
    await service.delete(enrollment_id=enrollment_id, org_id=admin.org_id)
    await db.commit()
    return Response(status_code=204)
