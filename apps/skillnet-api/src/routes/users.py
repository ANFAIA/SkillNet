"""User routes: admin management plus self-service profile."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from src.deps.auth import AdminUser, CurrentUser, OrganizationWorkspace
from src.deps.db import DBSession
from src.repositories.skill_repo import SkillRepository
from src.repositories.user_repo import UserRepository
from src.schemas.common import PaginatedResponse
from src.schemas.skill import UserSkillRead
from src.schemas.user import (
    EmployeeCreated,
    ResetPasswordRequest,
    UserAdminUpdate,
    UserCreateRequest,
    UserRead,
    UserSelfUpdate,
)
from src.services.skill_service import SkillService
from src.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


def _service(db: DBSession) -> UserService:
    return UserService(UserRepository(db))


def _skill_service(db: DBSession) -> SkillService:
    return SkillService(SkillRepository(db))


@router.get("", response_model=PaginatedResponse[UserRead])
async def list_users(
    admin: AdminUser,
    db: DBSession,
    _org: OrganizationWorkspace,
    search: Annotated[str | None, Query()] = None,
    role: Annotated[str | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PaginatedResponse[UserRead]:
    service = _service(db)
    rows, total = await service.list_users(
        org_id=admin.org_id,
        search=search,
        role=role,
        is_active=is_active,
        offset=offset,
        limit=limit,
    )
    return PaginatedResponse[UserRead](
        items=[UserRead.model_validate(u) for u in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("", response_model=EmployeeCreated, status_code=201)
async def create_user(
    admin: AdminUser, db: DBSession, body: UserCreateRequest, _org: OrganizationWorkspace
) -> EmployeeCreated:
    service = _service(db)
    user, temporary_password = await service.create_employee(
        org_id=admin.org_id,
        email=body.email,
        full_name=body.full_name,
        password=body.password,
    )
    await db.commit()
    return EmployeeCreated(
        **UserRead.model_validate(user).model_dump(),
        temporary_password=temporary_password,
    )


@router.get("/me", response_model=UserRead)
async def get_me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.put("/me", response_model=UserRead)
async def update_me(
    user: CurrentUser, db: DBSession, body: UserSelfUpdate
) -> UserRead:
    service = _service(db)
    updated = await service.update_self(
        user=user,
        full_name=body.full_name,
        learning_profile=body.learning_profile,
        accessibility=(
            body.accessibility.model_dump() if body.accessibility is not None else None
        ),
    )
    await db.commit()
    return UserRead.model_validate(updated)


@router.get("/me/skills", response_model=list[UserSkillRead])
async def get_my_skills(user: CurrentUser, db: DBSession) -> list[UserSkillRead]:
    service = _skill_service(db)
    skills = await service.get_user_skills(user.org_id, user.id)
    return [UserSkillRead(**s) for s in skills]


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    admin: AdminUser, db: DBSession, user_id: uuid.UUID, _org: OrganizationWorkspace
) -> UserRead:
    service = _service(db)
    user = await service.get_user(user_id, admin.org_id)
    return UserRead.model_validate(user)


@router.put("/{user_id}", response_model=UserRead)
async def update_user(
    admin: AdminUser,
    db: DBSession,
    user_id: uuid.UUID,
    body: UserAdminUpdate,
    _org: OrganizationWorkspace,
) -> UserRead:
    service = _service(db)
    user = await service.update_user(
        user_id=user_id,
        org_id=admin.org_id,
        full_name=body.full_name,
        role=body.role,
        is_active=body.is_active,
    )
    await db.commit()
    return UserRead.model_validate(user)


@router.post("/{user_id}/reset-password")
async def reset_password(
    admin: AdminUser,
    db: DBSession,
    user_id: uuid.UUID,
    body: ResetPasswordRequest,
    _org: OrganizationWorkspace,
) -> dict:
    service = _service(db)
    await service.reset_password(
        user_id=user_id,
        org_id=admin.org_id,
        admin_id=admin.id,
        new_password=body.new_password,
    )
    await db.commit()
    return {"ok": True}
