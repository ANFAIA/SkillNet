"""User request bodies. Responses reuse ``src.auth.schemas.UserRead``."""

from pydantic import BaseModel, EmailStr, Field

from src.auth.schemas import UserRead
from src.schemas.onboarding import AccessibilitySubmit

__all__ = [
    "UserRead",
    "UserCreateRequest",
    "EmployeeCreated",
    "UserAdminUpdate",
    "UserSelfUpdate",
    "ResetPasswordRequest",
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
    #: The four reading settings of question 5 (``users.accessibility``, §3.1).
    #: The onboarding wizard writes them through ``POST /onboarding``, which is
    #: the only atomic path (``learner_profiles`` + ``users`` in one tx, §11.2);
    #: this is the Settings-screen path for changing them afterwards. Validation
    #: is the *same* ``AccessibilitySubmit`` the wizard uses — ``extra='forbid'``,
    #: four known booleans — so no unknown flag can reach the jsonb column by
    #: either door. ``short_blocks`` feeds ``effective_density`` and therefore the
    #: ``cache_key`` (§3.1), so this has to persist or the setting is a lie.
    accessibility: AccessibilitySubmit | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=6)
