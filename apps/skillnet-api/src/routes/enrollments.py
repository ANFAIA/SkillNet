"""Enrollment routes: list, assign, detail with progress, and removal."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from src.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from src.deps.auth import AdminUser, CurrentUser, OrganizationWorkspace
from src.deps.db import DBSession
from src.models import Enrollment, EnrollmentStatus, UserRole
from src.repositories.course_folder_repo import CourseFolderRepository
from src.repositories.course_repo import CourseRepository
from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.exercise_repo import ExerciseRepository
from src.schemas.common import PaginatedResponse
from src.schemas.enrollment import (
    EnrollmentAssignmentResult,
    EnrollmentCreate,
    EnrollmentRead,
)
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
    is_learner_surface = user.role == UserRole.EMPLOYEE
    effective_user_id = user.id if is_learner_surface else user_id
    rows, total = await service.list_enrollments(
        org_id=user.org_id,
        user_id=effective_user_id,
        course_id=course_id,
        status=_parse_status(status),
        # This one endpoint is two surfaces. For a learner it is "My Courses", and a
        # course the admin archived has to disappear from it — that is what archiving
        # means. For an admin it is the employee record, where an archived course is
        # history worth seeing, so the admin branch keeps every row.
        include_archived_courses=not is_learner_surface,
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


async def _reload_created(
    service: EnrollmentService, created: list[Enrollment], org_id: uuid.UUID
) -> list[EnrollmentRead]:
    """Re-read what was just assigned, so the rows carry their course title.

    ``assign``/``assign_courses`` return the bare ORM objects; ``_read`` needs the
    ``course`` relationship, which only ``get_with_course`` loads.

    Progress is reported as 0.0 without computing it, as this route has always done. It
    is exact for a row created a line ago, and ``assign`` can now also return a row that
    already existed (it is idempotent), whose progress may not be zero — the caller of an
    *assignment* is telling the server what to enrol, not asking how far anyone got, and
    ``GET /enrollments`` is one request away with the computed number.
    """
    rows = []
    for enrollment in created:
        loaded = await service.get_scoped(enrollment_id=enrollment.id, org_id=org_id)
        rows.append(_read(loaded, 0.0))
    return rows


@router.post(
    "",
    response_model=list[EnrollmentRead] | EnrollmentAssignmentResult,
    status_code=201,
)
async def create_enrollments(
    admin: AdminUser, db: DBSession, body: EnrollmentCreate, _org: OrganizationWorkspace
) -> list[EnrollmentRead] | EnrollmentAssignmentResult:
    """Assign one course, or every published course of one folder, to these people.

    Two request shapes, two answers, and the older one is untouched:

    * ``{course_id, user_ids, deadline?}`` -> ``list[EnrollmentRead]``, exactly as
      before. Three screens send this and none of them had to change.
    * ``{folder_id, user_ids, deadline?}`` -> ``EnrollmentAssignmentResult``: the folder
      is a *set* of courses, so the caller needs to know how many enrollments were
      created and how many were skipped for already existing. See the schema for why
      that could not be squeezed into the list.

    ``EnrollmentCreate`` guarantees exactly one of the two is present (422 otherwise), so
    the branch below is a total function and neither ``if`` needs an ``else``.

    The folder branch enrolls **published** courses only, the same set as
    ``POST /course-folders/{id}/assign`` — the same repository call, so the two entry
    points cannot drift. A folder whose courses are all still drafts is not an error:
    it answers ``course_count: 0, created_count: 0``, and the caller is expected to say
    so out loud rather than report a successful assignment that enrolled nobody.
    """
    service = _service(db)
    if body.folder_id is not None:
        folder_repo = CourseFolderRepository(db)
        if await folder_repo.get_scoped(body.folder_id, admin.org_id) is None:
            # 404 and not 403: a folder of another organisation must not be
            # distinguishable from one that never existed.
            raise NotFoundError("course_folders", str(body.folder_id))
        course_ids = await folder_repo.list_published_course_ids(
            body.folder_id, admin.org_id
        )
        created, skipped = await service.assign_courses(
            org_id=admin.org_id,
            assigned_by=admin.id,
            course_ids=course_ids,
            user_ids=body.user_ids,
            deadline=body.deadline,
        )
        await db.commit()
        return EnrollmentAssignmentResult(
            course_count=len(course_ids),
            created_count=len(created),
            skipped_existing_count=skipped,
            enrollments=await _reload_created(service, created, admin.org_id),
        )

    # Narrowing only: the model validator has already guaranteed one of the two.
    assert body.course_id is not None
    created = await service.assign(
        org_id=admin.org_id,
        assigned_by=admin.id,
        course_id=body.course_id,
        user_ids=body.user_ids,
        deadline=body.deadline,
    )
    await db.commit()
    return await _reload_created(service, created, admin.org_id)


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
    admin: AdminUser, db: DBSession, enrollment_id: uuid.UUID, _org: OrganizationWorkspace
) -> Response:
    service = _service(db)
    await service.delete(enrollment_id=enrollment_id, org_id=admin.org_id)
    await db.commit()
    return Response(status_code=204)
