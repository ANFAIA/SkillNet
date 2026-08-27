"""User routes: admin management plus self-service profile."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from src.deps.auth import AdminUser, CurrentUser, IndividualWorkspace, OrganizationWorkspace
from src.deps.db import DBSession
from src.repositories.learner_profile_repo import LearnerProfileRepository
from src.repositories.skill_repo import SkillRepository
from src.repositories.user_repo import UserRepository
from src.schemas.common import PaginatedResponse
from src.schemas.skill import UserSkillRead
from src.schemas.user import (
    ChangeEmailRequest,
    ChangePasswordRequest,
    DeleteAccountRequest,
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
    group_id: Annotated[uuid.UUID | None, Query()] = None,
    exclude_group_id: Annotated[uuid.UUID | None, Query()] = None,
    ungrouped: Annotated[bool, Query()] = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PaginatedResponse[UserRead]:
    """The organization's people, filtered and paginated.

    ``group_id`` filters server-side on purpose, like every other filter here: the page
    the client holds is at most 100 rows, so narrowing it in the browser would only ever
    find the members who happened to be on it. An unknown group id is not an error, it
    is an empty page — the filter is a *view*, and a 404 would make a stale bookmark
    look like a broken screen.

    ``exclude_group_id`` is its complement, and it exists for the membership editor: the
    "add people" list must be people who are *not* in the group. Passing both is
    meaningless but not an error — it answers an empty page, which is the truth.

    ``ungrouped`` is a different question again: people in **no** group at all. It is the
    one an administrator actually asks — "who have I not covered?" — and without it a
    person can only be found by knowing in advance which group they are missing from.
    """
    service = _service(db)
    rows, total = await service.list_users(
        org_id=admin.org_id,
        search=search,
        role=role,
        is_active=is_active,
        group_id=group_id,
        exclude_group_id=exclude_group_id,
        ungrouped=ungrouped,
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
        role=body.role,
    )
    # Every employee is a learner. Create their learner-profile row now (onboarding
    # not yet completed) so the onboarding gate fires on their first login — without
    # it, a brand-new employee has no profile row, the profile endpoint 404s, and the
    # gate reads that as "do not redirect", silently skipping onboarding. See
    # docs/design/audience-modes.md.
    #
    # An administrator of an organization does not learn, so gets no profile row —
    # the same split `POST /setup` makes for the owner account.
    if body.role != "admin":
        await LearnerProfileRepository(db).get_or_create(
            user_id=user.id, org_id=admin.org_id
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


@router.post("/me/change-password")
async def change_password(
    user: CurrentUser, db: DBSession, body: ChangePasswordRequest
) -> dict:
    service = _service(db)
    await service.change_own_password(
        user=user,
        current_password=body.current_password,
        new_password=body.new_password,
    )
    await db.commit()
    return {"ok": True}


@router.put("/me/email", response_model=UserRead)
async def change_email(
    user: CurrentUser, db: DBSession, body: ChangeEmailRequest
) -> UserRead:
    service = _service(db)
    updated = await service.change_own_email(
        user=user,
        org_id=user.org_id,
        new_email=body.new_email,
        current_password=body.current_password,
    )
    await db.commit()
    return UserRead.model_validate(updated)


@router.delete("/me")
async def delete_account(
    user: CurrentUser, db: DBSession, body: DeleteAccountRequest, _mode: IndividualWorkspace
) -> dict:
    service = _service(db)
    await service.delete_own_account(user=user, current_password=body.current_password)
    await db.commit()
    return {"ok": True}


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
        actor_id=admin.id,
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
