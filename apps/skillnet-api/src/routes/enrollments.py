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
from src.services.enrollment_service import EnrollmentService, ResolvedAudience

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
    #: Capped at the row limit it exists to serve: a filter longer than the page it can
    #: return is a query whose answer nobody can use, and an uncapped ``IN`` list is a
    #: free way to make the database do arbitrary work.
    user_ids: Annotated[list[uuid.UUID] | None, Query(max_length=100)] = None,
    course_id: Annotated[uuid.UUID | None, Query()] = None,
    folder_id: Annotated[uuid.UUID | None, Query()] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PaginatedResponse[EnrollmentRead]:
    """List enrollments, scoped and filtered.

    ``user_ids`` and ``folder_id`` exist for one caller: a screen showing a *page* of
    people next to a *set* of courses, which needs "who of these holds what" in one
    bounded read. Asking per course and hoping the answer fits in 100 rows is how the
    folder-assignment dialog came to report people as unenrolled who were not.

    ``folder_id`` resolves to the folder's **published** courses — the same set every
    assignment path uses, via ``list_published_course_ids``, so the dialog's ticks and
    the button's effect cannot describe different sets of courses.
    """
    service = _service(db)
    # Employees only ever see their own enrollments.
    is_learner_surface = user.role == UserRole.EMPLOYEE
    effective_user_id = user.id if is_learner_surface else user_id
    # A learner asking about other people is answered about themselves, not refused: the
    # single-id filter has always behaved that way and the plural must not be a way
    # around it.
    effective_user_ids = None if is_learner_surface else user_ids
    course_ids = None
    if folder_id is not None:
        folder_repo = CourseFolderRepository(db)
        if await folder_repo.get_scoped(folder_id, user.org_id) is None:
            raise NotFoundError("course_folders", str(folder_id))
        # A folder with no published course filters to *nothing*, not to everything.
        course_ids = list(
            await folder_repo.list_published_course_ids(folder_id, user.org_id)
        )
    rows, total = await service.list_enrollments(
        org_id=user.org_id,
        user_id=effective_user_id,
        user_ids=effective_user_ids,
        course_id=course_id,
        course_ids=course_ids,
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


#: How many created rows an assignment answer echoes back.
#:
#: The echo is a convenience — the caller already knows what it ordered — and a group
#: assignment can create thousands of rows, at which point serialising them all is the
#: most expensive part of the request, for information nobody asked for. Past this many
#: the answer says so through ``enrollments_truncated`` rather than quietly returning a
#: prefix that reads like the whole set.
ENROLLMENT_ECHO_LIMIT = 100


async def _reload_created(
    service: EnrollmentService, created: list[Enrollment], org_id: uuid.UUID
) -> list[EnrollmentRead]:
    """Re-read what was just assigned, so the rows carry their course title.

    ``assign``/``assign_courses`` return the bare ORM objects; ``_read`` needs the
    ``course`` relationship, which only an eager load supplies. One query for the whole
    batch, not one per row: with groups in play a batch is no longer three rows.

    Progress is reported as 0.0 without computing it, as this route has always done. It
    is exact for a row created a line ago, and ``assign`` can now also return a row that
    already existed (it is idempotent), whose progress may not be zero — the caller of an
    *assignment* is telling the server what to enrol, not asking how far anyone got, and
    ``GET /enrollments`` is one request away with the computed number.

    The per-row ``get_scoped`` this replaced also re-checked the organization. Nothing is
    lost: every id here was produced by this request, against a course this route scoped
    to ``org_id`` before it wrote anything.
    """
    if not created:
        return []
    loaded = await service.enrollment_repo.list_with_courses(
        [enrollment.id for enrollment in created]
    )
    by_id = {enrollment.id: enrollment for enrollment in loaded}
    # Keep the order the service returned; the batch query has none of its own.
    return [
        _read(by_id[enrollment.id], 0.0)
        for enrollment in created
        if enrollment.id in by_id
    ]


async def _assignment_result(
    service: EnrollmentService,
    org_id: uuid.UUID,
    course_count: int,
    created: list[Enrollment],
    skipped: int,
    audience: ResolvedAudience,
) -> EnrollmentAssignmentResult:
    """The counts answer, shared by the folder branch and the group branch."""
    echoed = created[:ENROLLMENT_ECHO_LIMIT]
    return EnrollmentAssignmentResult(
        course_count=course_count,
        created_count=len(created),
        skipped_existing_count=skipped,
        person_count=len(audience.user_ids),
        skipped_inactive_count=audience.skipped_inactive,
        enrollments=await _reload_created(service, echoed, org_id),
        enrollments_truncated=len(created) > len(echoed),
    )


@router.post(
    "",
    response_model=list[EnrollmentRead] | EnrollmentAssignmentResult,
    status_code=201,
)
async def create_enrollments(
    admin: AdminUser, db: DBSession, body: EnrollmentCreate, _org: OrganizationWorkspace
) -> list[EnrollmentRead] | EnrollmentAssignmentResult:
    """Assign one course, or every published course of one folder, to these people.

    **Audience** is ``user_ids`` and/or ``group_ids``, unioned and deduplicated by
    ``resolve_audience`` — the one place a group ever becomes a list of people.
    **Target** is ``course_id`` or ``folder_id``, never both.

    Which answer comes back depends on the request, and the rule is exact:

    * ``{course_id, user_ids, deadline?}`` with no ``group_ids`` -> ``list[EnrollmentRead]``,
      byte for byte the response this endpoint has always given. Three screens send this
      shape and none of them had to change.
    * **Anything naming a folder or a group** -> ``EnrollmentAssignmentResult``. Both are
      sets the caller did not enumerate — a folder of courses, a group of people — so the
      outcome is counts: created, already there, people reached, inactive members skipped.
      A bare list carries none of that, and for a group it cannot even say how many people
      the order landed on.

    ``EnrollmentCreate`` guarantees exactly one target and at least one audience (422
    otherwise), so the branches below are total.

    The folder branch enrolls **published** courses only, the same set as
    ``POST /course-folders/{id}/assign`` — the same repository call, so the two entry
    points cannot drift. A folder whose courses are all still drafts is not an error:
    it answers ``course_count: 0, created_count: 0``, and the caller is expected to say
    so out loud rather than report a successful assignment that enrolled nobody.
    """
    service = _service(db)
    # Before any target lookup: an unknown group is a 404, and it must be a 404 that
    # wrote nothing rather than one discovered halfway through a folder.
    audience = await service.resolve_audience(
        org_id=admin.org_id, user_ids=body.user_ids, group_ids=body.group_ids
    )

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
            user_ids=audience.user_ids,
            deadline=body.deadline,
            source_group_by_user=audience.source_group_by_user,
        )
        await db.commit()
        return await _assignment_result(
            service, admin.org_id, len(course_ids), created, skipped, audience
        )

    # Narrowing only: the model validator has already guaranteed one of the two.
    assert body.course_id is not None
    if body.group_ids:
        # One course, but the caller named a set of people, so the answer is counts.
        # `assign_courses` with a single course is the same write as `assign` and is the
        # one that separates created from already-there — recovering that split from
        # `assign`'s row-per-person list is not possible without asking the database
        # again for something it just told us.
        created, skipped = await service.assign_courses(
            org_id=admin.org_id,
            assigned_by=admin.id,
            course_ids=[body.course_id],
            user_ids=audience.user_ids,
            deadline=body.deadline,
            source_group_by_user=audience.source_group_by_user,
        )
        await db.commit()
        return await _assignment_result(
            service, admin.org_id, 1, created, skipped, audience
        )

    created = await service.assign(
        org_id=admin.org_id,
        assigned_by=admin.id,
        course_id=body.course_id,
        user_ids=audience.user_ids,
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
