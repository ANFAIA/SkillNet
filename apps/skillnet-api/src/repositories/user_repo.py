"""User data access."""

import uuid
from collections.abc import Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.models import User, UserGroup, UserGroupMember, UserRole
from src.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)

    async def get_by_email(self, org_id: uuid.UUID, email: str) -> User | None:
        rows, _ = await self.list(
            filters=[User.org_id == org_id, User.email == email], limit=1
        )
        return rows[0] if rows else None

    async def get_by_google_sub(self, google_sub: str) -> User | None:
        """Look up an account by its external Google identity.

        Not scoped to an organization on purpose: `google_sub` is unique across the
        whole table (migration 0022), and at sign-in time there is no organization
        context yet — the account is what determines it.
        """
        rows, _ = await self.list(filters=[User.google_sub == google_sub], limit=1)
        return rows[0] if rows else None

    async def count_admins(
        self, org_id: uuid.UUID, *, exclude_user_id: uuid.UUID | None = None
    ) -> int:
        """How many *active* admins the organization would still have.

        Active only: a deactivated admin cannot sign in, so counting them would let
        the last usable administrator be demoted and lock everyone out.
        """
        filters: list[ColumnElement[bool]] = [
            User.org_id == org_id,
            User.role == UserRole.ADMIN,
            User.is_active.is_(True),
        ]
        if exclude_user_id is not None:
            filters.append(User.id != exclude_user_id)
        _, total = await self.list(filters=filters, limit=1)
        return total

    async def list_users(
        self,
        *,
        org_id: uuid.UUID,
        search: str | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
        group_id: uuid.UUID | None = None,
        exclude_group_id: uuid.UUID | None = None,
        ungrouped: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[User], int]:
        filters: list[ColumnElement[bool]] = [User.org_id == org_id]
        if search:
            pattern = f"%{search}%"
            filters.append(or_(User.full_name.ilike(pattern), User.email.ilike(pattern)))
        if role is not None:
            filters.append(User.role == role)
        if is_active is not None:
            filters.append(User.is_active == is_active)
        if group_id is not None:
            # A semijoin rather than a JOIN: `BaseRepository.list` counts with
            # `select(count()).select_from(User)`, and a join that duplicated a user
            # would inflate that total. `IN` cannot, whatever the membership rows say.
            filters.append(
                User.id.in_(
                    select(UserGroupMember.user_id).where(
                        UserGroupMember.group_id == group_id
                    )
                )
            )
        if ungrouped:
            # Nobody's group, not "not in *this* group". The join to `user_groups` scopes
            # the subquery to this organization: a membership row pointing at another
            # tenant's group must not make somebody look grouped here.
            filters.append(
                User.id.notin_(
                    select(UserGroupMember.user_id)
                    .join(UserGroup, UserGroup.id == UserGroupMember.group_id)
                    .where(UserGroup.org_id == org_id)
                )
            )
        if exclude_group_id is not None:
            # The complement of the filter above, and the reason it exists: the
            # "add people" half of the membership editor needs a page of people who are
            # *not* in the group. Computing that in the browser would mean intersecting
            # two paginated lists whose slices do not line up — the answer would be wrong
            # for anyone who fell on a different page, and wrong in the direction that
            # offers to add somebody who is already a member.
            filters.append(
                User.id.notin_(
                    select(UserGroupMember.user_id).where(
                        UserGroupMember.group_id == exclude_group_id
                    )
                )
            )
        return await self.list(
            filters=filters, order_by=User.full_name, offset=offset, limit=limit
        )
