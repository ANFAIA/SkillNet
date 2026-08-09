"""Authentication dependency injection: current-user and role guards."""

import uuid
from typing import Annotated

from fastapi import Depends
from fastapi_users import FastAPIUsers

from src.auth.backend import auth_backend
from src.auth.manager import get_user_manager
from src.core.exceptions import ForbiddenError
from src.models import User, UserRole

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


AdminUser = Annotated[User, Depends(require_admin)]
EmployeeUser = Annotated[User, Depends(require_employee)]
EmployeeOrAdminUser = Annotated[User, Depends(require_employee_or_admin)]
