"""User request bodies. Responses reuse ``src.auth.schemas.UserRead``."""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from src.auth.schemas import UserRead
from src.schemas.onboarding import AccessibilitySubmit

__all__ = [
    "UserRead",
    "GroupBrief",
    "UserListRead",
    "UserCreateRequest",
    "EmployeeCreated",
    "UserAdminUpdate",
    "UserSelfUpdate",
    "ResetPasswordRequest",
    "ChangePasswordRequest",
    "ChangeEmailRequest",
    "DeleteAccountRequest",
]


class GroupBrief(BaseModel):
    """A group as it appears on somebody's row: enough to name it and to filter by it.

    Deliberately not ``UserGroupRead``: that carries ``member_count``, which is a
    correlated subquery per group and answers a question the row is not asking. A page
    of twenty-five people would pay for it twenty-five times over to render a name.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class UserListRead(UserRead):
    """One row of ``GET /users``.

    ``groups`` is ``None`` unless ``with_groups=true`` was asked for, and that is not the
    same as ``[]``. Most callers of this endpoint only need names and ids — the people
    pickers, the course-assignment dialogs, the one-row count probes — and they must not
    pay for a membership read they never render. A caller that *did* ask, meanwhile, has
    to be able to tell "this person is in no group" from "nobody asked".
    """

    groups: list[GroupBrief] | None = None


class UserCreateRequest(BaseModel):
    email: EmailStr
    full_name: str
    # Optional: admin may set the employee's initial password. If omitted, the
    # server generates a temporary one and returns it once (see EmployeeCreated).
    password: str | None = Field(default=None, min_length=8)
    #: `admin` is how an administrator invites another administrator. Only the two
    #: roles exist, and the literal is what refuses a third: an unknown value is a
    #: 422 at the edge rather than a `ValidationError` deeper in the service.
    role: Literal["admin", "employee"] = "employee"


class EmployeeCreated(UserRead):
    # Populated only when the server generated the password; the admin must
    # hand it to the employee. Null when the admin supplied the password.
    temporary_password: str | None = None


class UserAdminUpdate(BaseModel):
    full_name: str | None = None
    #: Promote to admin or demote to employee. Constrained to the two roles that
    #: exist; the service additionally refuses any change that would leave the
    #: organization with no active administrator.
    role: Literal["admin", "employee"] | None = None
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
    new_password: str = Field(min_length=8)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class ChangeEmailRequest(BaseModel):
    new_email: EmailStr
    current_password: str


class DeleteAccountRequest(BaseModel):
    current_password: str
