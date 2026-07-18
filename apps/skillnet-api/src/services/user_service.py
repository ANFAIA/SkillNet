"""User business logic: employee creation and profile updates."""

import secrets
import uuid
from collections.abc import Sequence

from fastapi_users.password import PasswordHelper

from src.core.exceptions import ConflictError, NotFoundError, ValidationError
from src.models import LearningProfile, User, UserRole
from src.repositories.user_repo import UserRepository

_password_helper = PasswordHelper()


def _to_enum(enum_cls: type, value: str, field: str) -> object:
    try:
        return enum_cls(value)
    except ValueError as exc:
        raise ValidationError(f"Invalid {field}: {value}", field=field) from exc


class UserService:
    def __init__(self, repo: UserRepository) -> None:
        self.repo = repo

    async def list_users(
        self,
        *,
        org_id: uuid.UUID,
        search: str | None,
        role: str | None,
        is_active: bool | None,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[User], int]:
        role_enum = _to_enum(UserRole, role, "role") if role else None
        return await self.repo.list_users(
            org_id=org_id,
            search=search,
            role=role_enum,  # type: ignore[arg-type]
            is_active=is_active,
            offset=offset,
            limit=limit,
        )

    async def get_user(self, user_id: uuid.UUID, org_id: uuid.UUID) -> User:
        user = await self.repo.get_by_id(user_id)
        if user is None or user.org_id != org_id:
            raise NotFoundError("users", str(user_id))
        return user

    async def create_employee(
        self, *, org_id: uuid.UUID, email: str, full_name: str
    ) -> User:
        if await self.repo.get_by_email(org_id, email) is not None:
            raise ConflictError("A user with this email already exists", field="email")
        hashed_password = _password_helper.hash(secrets.token_urlsafe(16))
        return await self.repo.create(
            org_id=org_id,
            email=email,
            full_name=full_name,
            hashed_password=hashed_password,
            role=UserRole.EMPLOYEE,
            learning_profile=LearningProfile.STANDARD,
            is_active=True,
        )

    async def update_user(
        self,
        *,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        full_name: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> User:
        user = await self.get_user(user_id, org_id)
        changes: dict = {}
        if full_name is not None:
            changes["full_name"] = full_name
        if role is not None:
            changes["role"] = _to_enum(UserRole, role, "role")
        if is_active is not None:
            changes["is_active"] = is_active
        if not changes:
            return user
        return await self.repo.update(user, **changes)

    async def update_self(
        self,
        *,
        user: User,
        full_name: str | None = None,
        learning_profile: str | None = None,
    ) -> User:
        changes: dict = {}
        if full_name is not None:
            changes["full_name"] = full_name
        if learning_profile is not None:
            changes["learning_profile"] = _to_enum(
                LearningProfile, learning_profile, "learning_profile"
            )
        if not changes:
            return user
        return await self.repo.update(user, **changes)
