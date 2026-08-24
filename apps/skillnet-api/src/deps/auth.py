"""Authentication dependency injection: current-user and role guards."""

import uuid
from typing import Annotated

from fastapi import Depends
from fastapi_users import FastAPIUsers
from sqlalchemy import select

from src.auth.backend import auth_backend
from src.auth.manager import get_user_manager
from src.core.exceptions import AppError, ForbiddenError
from src.deps.db import DBSession
from src.models import Organization, User, UserRole, WorkspaceMode

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

current_user = fastapi_users.current_user(active=True)
current_optional_user = fastapi_users.current_user(active=True, optional=True)

CurrentUser = Annotated[User, Depends(current_user)]


def _role_value(role: object) -> str:
    return role.value if isinstance(role, UserRole) else str(role)


def require_admin(user: CurrentUser) -> User:
    if _role_value(user.role) != UserRole.ADMIN.value:
        raise ForbiddenError("Admin access required")
    return user


def require_employee(user: CurrentUser) -> User:
    if _role_value(user.role) != UserRole.EMPLOYEE.value:
        raise ForbiddenError("Employee access required")
    return user


def require_employee_or_admin(user: CurrentUser) -> User:
    """The learner tutor, open to admins previewing a course (``/admin/probar-curso``).

    An admin testing a course walks the same node screens as the learner, so they
    need the same lesson tutor — not the org assistant on ``/chat/admin``. Both roles
    are the only ones that exist, so this is "any active user"; it stays an explicit
    allow-list rather than dropping the guard, so a future third role is denied by
    default.
    """
    if _role_value(user.role) not in (UserRole.EMPLOYEE.value, UserRole.ADMIN.value):
        raise ForbiddenError("Employee access required")
    return user


async def require_organization_workspace(user: CurrentUser, db: DBSession) -> None:
    """Gate collective, organization-only surfaces (employees, talent, stats,
    course assignment, skills catalogue).

    In an ``individual`` deployment these concepts do not exist, so the endpoints
    answer 404 rather than 403: it is not that the caller is *forbidden*, it is
    that there is no such thing in this workspace. This is server-side
    enforcement — hiding the sections in the SPA is UX, not authorization. See
    ``docs/design/audience-modes.md``.

    Scoped to the caller's own organization (``user.org_id``) rather than the
    ``select().limit(1)`` single-tenant shortcut, so it stays correct even if a
    database holds more than one organization row. Composes with the role guards
    (``AdminUser``) already on these endpoints.
    """
    mode = (
        await db.execute(
            select(Organization.workspace_mode).where(Organization.id == user.org_id)
        )
    ).scalar_one_or_none()
    if mode == WorkspaceMode.INDIVIDUAL:
        raise AppError(
            message="Not available in an individual workspace",
            code="NOT_FOUND",
            status_code=404,
        )


async def require_individual_workspace(user: CurrentUser, db: DBSession) -> None:
    """Gate the self-service "delete my account" endpoint to `individual` workspaces.

    An organization has no self-delete path: the admin represents the whole org, so
    deleting them would orphan it. That needs an explicit ownership-transfer flow,
    which does not exist yet — out of scope here. In `individual` mode the account
    holder is the only person the deletion affects, so it is safe to self-serve.
    """
    mode = (
        await db.execute(
            select(Organization.workspace_mode).where(Organization.id == user.org_id)
        )
    ).scalar_one_or_none()
    if mode != WorkspaceMode.INDIVIDUAL:
        raise AppError(
            message="Account deletion is only self-service in an individual workspace",
            code="NOT_FOUND",
            status_code=404,
        )


AdminUser = Annotated[User, Depends(require_admin)]
EmployeeUser = Annotated[User, Depends(require_employee)]
EmployeeOrAdminUser = Annotated[User, Depends(require_employee_or_admin)]
IndividualWorkspace = Annotated[None, Depends(require_individual_workspace)]
OrganizationWorkspace = Annotated[None, Depends(require_organization_workspace)]
