"""User business logic: employee creation and profile updates."""

import secrets
import uuid
from collections.abc import Mapping, Sequence

from fastapi_users.password import PasswordHelper

from src.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from src.models import LearningProfile, User, UserGroup, UserRole
from src.repositories.user_repo import UserRepository

_password_helper = PasswordHelper()


def _role_of(user: User) -> UserRole:
    """The stored role as an enum. SQLAlchemy hands back the enum; the fakes used by
    the unit tests hand back its string value, and both have to compare the same."""
    role = user.role
    return role if isinstance(role, UserRole) else UserRole(str(role))


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
        group_id: uuid.UUID | None = None,
        exclude_group_id: uuid.UUID | None = None,
        ungrouped: bool = False,
    ) -> tuple[Sequence[User], int]:
        role_enum = _to_enum(UserRole, role, "role") if role else None
        return await self.repo.list_users(
            org_id=org_id,
            search=search,
            role=role_enum,  # type: ignore[arg-type]
            is_active=is_active,
            group_id=group_id,
            exclude_group_id=exclude_group_id,
            ungrouped=ungrouped,
            offset=offset,
            limit=limit,
        )

    async def groups_of_users(
        self, user_ids: Sequence[uuid.UUID], org_id: uuid.UUID
    ) -> dict[uuid.UUID, list[UserGroup]]:
        """The groups of the people on one page, keyed by person.

        A separate call rather than an argument to ``list_users`` so that the page read
        keeps its shape — ``(rows, total)``, the one every other caller destructures —
        and the second, bounded read is visible at the call site instead of hidden
        behind a flag.
        """
        return await self.repo.groups_of_users(user_ids, org_id)

    async def get_user(self, user_id: uuid.UUID, org_id: uuid.UUID) -> User:
        user = await self.repo.get_by_id(user_id)
        if user is None or user.org_id != org_id:
            raise NotFoundError("users", str(user_id))
        return user

    async def create_employee(
        self,
        *,
        org_id: uuid.UUID,
        email: str,
        full_name: str,
        password: str | None = None,
        role: str | None = None,
    ) -> tuple[User, str | None]:
        """Create a member of the organization. Returns the user and, when the
        password was auto-generated, its plaintext value (so the admin can share it).

        `role` defaults to `employee`; passing `"admin"` is how an administrator
        invites another administrator. The caller is already required to be an admin
        of `org_id` by the route guard, and `org_id` comes from the *caller's* own
        account, never from the request body — that is what keeps one organization's
        admin out of another's user list.
        """
        if await self.repo.get_by_email(org_id, email) is not None:
            raise ConflictError("A user with this email already exists", field="email")
        generated: str | None = None
        if password:
            raw_password = password
        else:
            raw_password = secrets.token_urlsafe(9)
            generated = raw_password
        user = await self.repo.create(
            org_id=org_id,
            email=email,
            full_name=full_name,
            hashed_password=_password_helper.hash(raw_password),
            role=_to_enum(UserRole, role, "role") if role else UserRole.EMPLOYEE,
            learning_profile=LearningProfile.STANDARD,
            is_active=True,
        )
        return user, generated

    async def update_user(
        self,
        *,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        full_name: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> User:
        """Admin edit of another account, including its role.

        `get_user` scopes the lookup to `org_id` and 404s otherwise, so an admin of
        one organization cannot even *see* a user of another, let alone promote or
        demote them. `org_id` is always the caller's own — the route reads it from
        the authenticated admin, not from the path or body.
        """
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
        await self._guard_last_admin(
            user=user,
            org_id=org_id,
            actor_id=actor_id,
            new_role=changes.get("role"),
            new_is_active=changes.get("is_active"),
        )
        return await self.repo.update(user, **changes)

    async def _guard_last_admin(
        self,
        *,
        user: User,
        org_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        new_role: UserRole | None,
        new_is_active: bool | None,
    ) -> None:
        """Refuse any edit that would leave the organization with no usable admin.

        Two ways to reach the same dead end, so both are checked here rather than at
        the two call sites: demoting the last admin to employee, and deactivating
        them. Either one locks every remaining person out of user management
        permanently, with no in-app way back — the recovery is a hand-written SQL
        UPDATE on the server, which is not a thing a product should require.
        """
        if _role_of(user) is not UserRole.ADMIN:
            return
        loses_admin = new_role is not None and new_role is not UserRole.ADMIN
        loses_access = new_is_active is False
        if not (loses_admin or loses_access):
            return
        if await self.repo.count_admins(org_id, exclude_user_id=user.id) > 0:
            return
        if actor_id is not None and actor_id == user.id:
            raise ForbiddenError(
                "You are the only administrator of this organization. Promote "
                "someone else before changing your own role."
            )
        raise ForbiddenError(
            "This is the only administrator of this organization. Promote someone "
            "else first."
        )

    async def reset_password(
        self,
        *,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        admin_id: uuid.UUID,
        new_password: str,
    ) -> User:
        if user_id == admin_id:
            raise ForbiddenError("Cannot reset your own password through this endpoint")
        user = await self.get_user(user_id, org_id)
        return await self.repo.update(
            user, hashed_password=_password_helper.hash(new_password)
        )

    async def update_self(
        self,
        *,
        user: User,
        full_name: str | None = None,
        learning_profile: str | None = None,
        accessibility: Mapping[str, bool] | None = None,
    ) -> User:
        changes: dict = {}
        if full_name is not None:
            changes["full_name"] = full_name
        if learning_profile is not None:
            changes["learning_profile"] = _to_enum(
                LearningProfile, learning_profile, "learning_profile"
            )
        if accessibility is not None:
            # Replace, never merge: the Settings screen submits the four
            # checkboxes as a whole, so an unchecked box has to be able to turn
            # a stored `true` back off. Same normalization the onboarding path
            # applies (`learner_profile_service.complete_onboarding`), so the
            # jsonb holds plain booleans whichever door wrote it.
            changes["accessibility"] = {k: bool(v) for k, v in accessibility.items()}
        if not changes:
            return user
        return await self.repo.update(user, **changes)

    async def change_own_password(
        self, *, user: User, current_password: str, new_password: str
    ) -> None:
        verified, _ = _password_helper.verify_and_update(
            current_password, user.hashed_password
        )
        if not verified:
            raise ValidationError(
                "Current password is incorrect", field="current_password"
            )
        await self.repo.update(user, hashed_password=_password_helper.hash(new_password))

    async def change_own_email(
        self, *, user: User, org_id: uuid.UUID, new_email: str, current_password: str
    ) -> User:
        verified, _ = _password_helper.verify_and_update(
            current_password, user.hashed_password
        )
        if not verified:
            raise ValidationError("Password is incorrect", field="current_password")
        if new_email != user.email and await self.repo.get_by_email(org_id, new_email):
            raise ConflictError("A user with this email already exists", field="email")
        return await self.repo.update(user, email=new_email)

    async def delete_own_account(self, *, user: User, current_password: str) -> None:
        """Soft-delete: deactivate and scramble the email rather than a hard row
        delete. `user_id` is referenced from a couple dozen tables (enrollments,
        chat sessions, learning events, generation jobs, ...) without a cascade
        rule defined for most of them — a real DELETE would either 500 on the
        first FK it hits or (if a cascade *is* set somewhere) silently take
        unrelated history with it. Deactivating plus freeing the email gets the
        actual outcome the user wants (can't log in, can sign up again with the
        same address) without that risk.
        """
        verified, _ = _password_helper.verify_and_update(
            current_password, user.hashed_password
        )
        if not verified:
            raise ValidationError("Password is incorrect", field="current_password")
        scrambled_email = f"deleted-{user.id}@deleted.local"
        await self.repo.update(
            user, is_active=False, email=scrambled_email
        )
