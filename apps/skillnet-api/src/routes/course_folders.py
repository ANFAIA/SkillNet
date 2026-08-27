"""Admin course-library folder routes."""

import uuid

from fastapi import APIRouter, Response

from src.models.base import as_utc
from src.core.exceptions import NotFoundError
from src.deps.auth import AdminUser, OrganizationWorkspace
from src.deps.db import DBSession
from src.repositories.course_folder_repo import CourseFolderRepository
from src.repositories.course_repo import CourseRepository
from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.exercise_repo import ExerciseRepository
from src.schemas.course_folder import (
    CourseFolderAssignmentCreate,
    CourseFolderAssignmentResult,
    CourseFolderRead,
    CourseFolderWrite,
)
from src.services.course_folder_service import CourseFolderService
from src.services.enrollment_service import EnrollmentService

router = APIRouter(prefix="/course-folders", tags=["Course library"])


def _service(db: DBSession) -> CourseFolderService:
    return CourseFolderService(CourseFolderRepository(db))


def _read(folder, count: int = 0) -> CourseFolderRead:
    return CourseFolderRead(
        id=folder.id,
        name=folder.name,
        course_count=count,
        created_at=folder.created_at,
        updated_at=as_utc(folder.updated_at),
    )


@router.get("", response_model=list[CourseFolderRead])
async def list_folders(admin: AdminUser, db: DBSession) -> list[CourseFolderRead]:
    rows = await _service(db).list(admin.org_id)
    return [_read(folder, count) for folder, count in rows]


@router.post("", response_model=CourseFolderRead, status_code=201)
async def create_folder(
    admin: AdminUser, db: DBSession, body: CourseFolderWrite
) -> CourseFolderRead:
    folder = await _service(db).create(org_id=admin.org_id, name=body.name)
    await db.commit()
    return _read(folder)


@router.put("/{folder_id}", response_model=CourseFolderRead)
async def update_folder(
    admin: AdminUser,
    db: DBSession,
    folder_id: uuid.UUID,
    body: CourseFolderWrite,
) -> CourseFolderRead:
    folder = await _service(db).update(
        org_id=admin.org_id, folder_id=folder_id, name=body.name
    )
    await db.commit()
    return _read(folder)


@router.delete("/{folder_id}", status_code=204)
async def delete_folder(
    admin: AdminUser, db: DBSession, folder_id: uuid.UUID
) -> Response:
    await _service(db).delete(org_id=admin.org_id, folder_id=folder_id)
    await db.commit()
    return Response(status_code=204)


@router.post(
    "/{folder_id}/assign",
    response_model=CourseFolderAssignmentResult,
)
async def assign_folder(
    admin: AdminUser,
    db: DBSession,
    folder_id: uuid.UUID,
    body: CourseFolderAssignmentCreate,
    _org: OrganizationWorkspace,
) -> CourseFolderAssignmentResult:
    folder_repo = CourseFolderRepository(db)
    folder = await folder_repo.get_scoped(folder_id, admin.org_id)
    if folder is None:
        raise NotFoundError("course_folders", str(folder_id))
    course_ids = await folder_repo.list_published_course_ids(folder_id, admin.org_id)
    enrollment_service = EnrollmentService(
        EnrollmentRepository(db), CourseRepository(db), ExerciseRepository(db)
    )
    # Groups are resolved by the same call `POST /enrollments` uses, so the two doors
    # into "assign this folder" cannot disagree about who is in a group either.
    audience = await enrollment_service.resolve_audience(
        org_id=admin.org_id, user_ids=body.user_ids, group_ids=body.group_ids
    )
    created, skipped = await enrollment_service.assign_courses(
        org_id=admin.org_id,
        assigned_by=admin.id,
        course_ids=course_ids,
        user_ids=audience.user_ids,
        deadline=body.deadline,
        source_group_by_user=audience.source_group_by_user,
    )
    await db.commit()
    return CourseFolderAssignmentResult(
        course_count=len(course_ids),
        created_count=len(created),
        skipped_existing_count=skipped,
        person_count=len(audience.user_ids),
        skipped_inactive_count=audience.skipped_inactive,
    )
