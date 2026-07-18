"""User request bodies. Responses reuse ``src.auth.schemas.UserRead``."""

from pydantic import BaseModel, EmailStr, Field

from src.auth.schemas import UserRead

__all__ = [
    "UserRead",
    "UserCreateRequest",
    "EmployeeCreated",
    "UserAdminUpdate",
    "UserSelfUpdate",
]


class UserCreateRequest(BaseModel):
    email: EmailStr
    full_name: str
    # Optional: admin may set the employee's initial password. If omitted, the
    # server generates a temporary one and returns it once (see EmployeeCreated).
    password: str | None = Field(default=None, min_length=8)


class EmployeeCreated(UserRead):
    # Populated only when the server generated the password; the admin must
    # hand it to the employee. Null when the admin supplied the password.
    temporary_password: str | None = None


class UserAdminUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None


class UserSelfUpdate(BaseModel):
    full_name: str | None = None
    learning_profile: str | None = None
