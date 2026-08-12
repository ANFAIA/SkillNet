"""Admin course-library folder routes."""

import uuid

from fastapi import APIRouter, Response

from src.deps.auth import AdminUser
from src.deps.db import DBSession
from src.repositories.course_folder_repo import CourseFolderRepository
from src.schemas.course_folder import CourseFolderRead, CourseFolderWrite
from src.services.course_folder_service import CourseFolderService

router = APIRouter(prefix="/course-folders", tags=["Course library"])


def _service(db: DBSession) -> CourseFolderService:
    return CourseFolderService(CourseFolderRepository(db))


def _read(folder, count: int = 0) -> CourseFolderRead:
    return CourseFolderRead(
        id=folder.id,
        name=folder.name,
        course_count=count,
        created_at=folder.created_at,
        updated_at=folder.updated_at,
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
