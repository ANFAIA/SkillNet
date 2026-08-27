"""Persistence for the intentionally flat people-group registry."""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.models import User, UserGroup, UserGroupMember
from src.repositories.base import BaseRepository


class UserGroupRepository(BaseRepository[UserGroup]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, UserGroup)

    async def get_scoped(
        self, group_id: uuid.UUID, org_id: uuid.UUID
    ) -> UserGroup | None:
        stmt = select(UserGroup).where(
            UserGroup.id == group_id, UserGroup.org_id == org_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_name(self, org_id: uuid.UUID, name: str) -> UserGroup | None:
        stmt = select(UserGroup).where(
            UserGroup.org_id == org_id,
            func.lower(UserGroup.name) == name.casefold(),
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_with_counts(
        self,
        org_id: uuid.UUID,
        *,
        search: str | None = None,
        exclude_user_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[tuple[UserGroup, int]], int]:
        """One page of the organization's groups with their member counts, by name.

        Counts memberships, not *enrollable* people: a deactivated member is still a
        member. The assignment result is where the distinction is reported, because
        that is where it changes what happened.

        Paginated and searchable for the same reason ``list_users`` is: there is no
        ceiling on how many groups an organization has, and a rail that renders all of
        them is a rail that stops being usable at some size nobody chose. ``search``
        matches the name case-insensitively **in SQL** — filtering the page already
        fetched would only ever find the groups that happened to land on it.

        The member count is a correlated subquery, not the ``GROUP BY`` over an
        ``outerjoin`` this used to be: with ``LIMIT``/``OFFSET`` and a separate
        ``count(*)`` for the total, a join that multiplied a group by its memberships
        would both paginate the wrong rows and report a total of *memberships*.

        ``exclude_user_id`` is the mirror of ``list_users(exclude_group_id=...)``: the
        groups this person is **not** in, which is the only sensible thing to offer on
        their record. Excluded here rather than in the browser for the reason the whole
        parameter list exists — a page is not the collection, so dropping the person's
        groups from the page they happened to fall on leaves the ones on other pages
        offered, and the offer does nothing.
        """
        filters: list[ColumnElement[bool]] = [UserGroup.org_id == org_id]
        if search:
            filters.append(UserGroup.name.ilike(f"%{search}%"))
        if exclude_user_id is not None:
            filters.append(
                UserGroup.id.notin_(
                    select(UserGroupMember.group_id).where(
                        UserGroupMember.user_id == exclude_user_id
                    )
                )
            )
        member_count = (
            select(func.count(UserGroupMember.id))
            .where(UserGroupMember.group_id == UserGroup.id)
            .correlate(UserGroup)
            .scalar_subquery()
        )
        stmt = (
            select(UserGroup, member_count)
            .where(*filters)
            .order_by(func.lower(UserGroup.name))
            .offset(offset)
            .limit(limit)
        )
        count_stmt = select(func.count()).select_from(UserGroup).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()
        rows = list((await self.session.execute(stmt)).tuples().all())
        return rows, total

    async def scoped_ids(
        self, group_ids: Sequence[uuid.UUID], org_id: uuid.UUID
    ) -> set[uuid.UUID]:
        """Which of these groups exist in this organization.

        The caller compares against what it asked for, so a group of another tenant is
        indistinguishable from one that never existed — the same 404-not-403 rule the
        folder routes follow.
        """
        if not group_ids:
            return set()
        stmt = select(UserGroup.id).where(
            UserGroup.id.in_(set(group_ids)), UserGroup.org_id == org_id
        )
        return set((await self.session.scalars(stmt)).all())

    async def memberships(
        self, group_ids: Sequence[uuid.UUID], org_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, uuid.UUID, bool]]:
        """``(group_id, user_id, is_active)`` for every membership of these groups.

        One query for every group at once — expanding group by group would multiply
        round-trips by the number of groups for no gain.

        Rows, not a deduplicated list of people: who is in *which* group is what lets the
        service stamp an enrollment with the group it came from, and a flattened union
        throws that away. Deduplication and the active/inactive split are policy and live
        in ``EnrollmentService.resolve_audience``.

        The ``User.org_id`` filter is redundant with the group's own scoping and is kept
        deliberately: it is the last line between a membership row that should not exist
        and an enrollment in the wrong tenant.

        Ordered so the expansion is deterministic — two identical requests must enrol
        people in the same order, or a retry looks like a different operation.
        """
        if not group_ids:
            return []
        stmt = (
            select(UserGroupMember.group_id, User.id, User.is_active)
            .join(UserGroupMember, UserGroupMember.user_id == User.id)
            .where(
                UserGroupMember.group_id.in_(set(group_ids)),
                User.org_id == org_id,
            )
            .order_by(User.full_name, User.id)
        )
        return [(row[0], row[1], row[2]) for row in (await self.session.execute(stmt)).all()]

    async def groups_of_user(
        self, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> Sequence[tuple[UserGroup, int]]:
        """The groups one person belongs to, with each group's total member count.

        The counterpart of ``list_members``, and the read the *person's* record needs:
        "which groups is this person in" is a question the group-side listing can only
        answer by fetching every group and every membership.

        The member count comes from a correlated subquery rather than a second join, so
        the outer row set stays one per group — joining the memberships twice would
        multiply the rows and inflate every count.
        """
        member_count = (
            select(func.count(UserGroupMember.id))
            .where(UserGroupMember.group_id == UserGroup.id)
            .correlate(UserGroup)
            .scalar_subquery()
        )
        stmt = (
            select(UserGroup, member_count)
            .join(UserGroupMember, UserGroupMember.group_id == UserGroup.id)
            .where(
                UserGroupMember.user_id == user_id,
                UserGroup.org_id == org_id,
            )
            .order_by(func.lower(UserGroup.name))
        )
        return list((await self.session.execute(stmt)).tuples().all())

    async def list_members(
        self,
        group_id: uuid.UUID,
        *,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[User], int]:
        filters = [UserGroupMember.group_id == group_id]
        stmt = (
            select(User)
            .join(UserGroupMember, UserGroupMember.user_id == User.id)
            .where(*filters)
            # `User.id` breaks the tie. Ordering by a non-unique column alone leaves the
            # order of equal rows up to the planner, and it need not choose the same one
            # twice: two members sharing a name (or with none) could then appear on both
            # page 1 and page 2 while a third appears on neither — and the membership
            # editor would stage a removal against a row the admin never saw. Same
            # reasoning as `memberships` above.
            .order_by(User.full_name, User.id)
            .offset(offset)
            .limit(limit)
        )
        count_stmt = (
            select(func.count())
            .select_from(UserGroupMember)
            .join(User, UserGroupMember.user_id == User.id)
            .where(*filters)
        )
        rows = (await self.session.scalars(stmt)).all()
        total = (await self.session.execute(count_stmt)).scalar_one()
        return rows, total

    async def add_members(
        self, group_id: uuid.UUID, user_ids: Sequence[uuid.UUID]
    ) -> int:
        """Add these people, ignoring the ones already in. Returns how many were new.

        ``ON CONFLICT DO NOTHING`` rather than read-then-insert: two admins ticking the
        same person at the same time is an everyday race, and the loser would otherwise
        violate ``uq_user_group_members_pair`` and take the whole request down with an
        ``IntegrityError`` that is not an ``AppError`` — a 500. One statement, no
        savepoint, no loop.
        """
        wanted = list(dict.fromkeys(user_ids))
        if not wanted:
            return 0
        stmt = (
            pg_insert(UserGroupMember)
            .values([{"group_id": group_id, "user_id": uid} for uid in wanted])
            .on_conflict_do_nothing(constraint="uq_user_group_members_pair")
            .returning(UserGroupMember.id)
        )
        return len((await self.session.scalars(stmt)).all())

    async def remove_members(
        self, group_id: uuid.UUID, user_ids: Sequence[uuid.UUID]
    ) -> int:
        wanted = set(user_ids)
        if not wanted:
            return 0
        stmt = (
            delete(UserGroupMember)
            .where(
                UserGroupMember.group_id == group_id,
                UserGroupMember.user_id.in_(wanted),
            )
            .returning(UserGroupMember.id)
            # An ORM-enabled DELETE defaults to synchronizing the identity map, which
            # with RETURNING means a second SELECT for rows nothing in this request
            # holds. Nothing here reads a membership object afterwards.
            .execution_options(synchronize_session=False)
        )
        return len((await self.session.scalars(stmt)).all())
