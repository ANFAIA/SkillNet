"""User request bodies. Responses reuse ``src.auth.schemas.UserRead``."""

from pydantic import BaseModel, EmailStr

from src.auth.schemas import UserRead

__all__ = ["UserRead", "UserCreateRequest", "UserAdminUpdate", "UserSelfUpdate"]


class UserCreateRequest(BaseModel):
    email: EmailStr
    full_name: str


class UserAdminUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None


class UserSelfUpdate(BaseModel):
    full_name: str | None = None
    learning_profile: str | None = None
