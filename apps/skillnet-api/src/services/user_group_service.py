"""Business rules for people groups: naming, membership, and tenant safety."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select

from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.models import User, UserGroup
from src.repositories.user_group_repo import UserGroupRepository


class UserGroupService:
    """The only place a group is created, named, or has its membership changed.

    Deliberately thin, in the spirit of ``CourseFolderService``: a group has a name and
    a list of people and no powers of its own. What a group *does* — put training on
    several people at once — belongs to ``EnrollmentService``, which is where every
    other assignment already lives.
    """

    def __init__(self, repo: UserGroupRepository) -> None:
        self.repo = repo

    async def list(
        self,
        org_id: uuid.UUID,
        *,
        search: str | None = None,
        exclude_user_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[tuple[UserGroup, int]], int]:
        """One page of groups, and how many match in total.

        Paginated like the people list beside it. A rail that renders every group is
        fine at three and unusable at three hundred, and "how many are there really" is
        a question only the total can answer.
        """
        return await self.repo.list_with_counts(
            org_id,
            search=search,
            exclude_user_id=exclude_user_id,
            offset=offset,
            limit=limit,
        )

    async def get(self, *, org_id: uuid.UUID, group_id: uuid.UUID) -> UserGroup:
        group = await self.repo.get_scoped(group_id, org_id)
        if group is None:
            # 404 rather than 403: a group of another organization must not be
            # distinguishable from one that never existed.
            raise NotFoundError("user_groups", str(group_id))
        return group

    async def create(self, *, org_id: uuid.UUID, name: str) -> UserGroup:
        if await self.repo.get_by_name(org_id, name):
            raise ConflictError("A group with this name already exists", field="name")
        return await self.repo.create(org_id=org_id, name=name)

    async def update(
        self, *, org_id: uuid.UUID, group_id: uuid.UUID, name: str
    ) -> UserGroup:
        group = await self.get(org_id=org_id, group_id=group_id)
        duplicate = await self.repo.get_by_name(org_id, name)
        if duplicate is not None and duplicate.id != group.id:
            raise ConflictError("A group with this name already exists", field="name")
        return await self.repo.update(group, name=name)

    async def delete(self, *, org_id: uuid.UUID, group_id: uuid.UUID) -> None:
        """Delete the group and its memberships. Training is never touched.

        ``enrollments.source_group_id`` is ``ON DELETE SET NULL``, so the courses the
        group assigned stay exactly where they are and only lose the note saying who put
        them there. Deleting a list of names must not un-enrol anybody.
        """
        group = await self.get(org_id=org_id, group_id=group_id)
        await self.repo.delete(group)

    async def list_members(
        self, *, org_id: uuid.UUID, group_id: uuid.UUID, offset: int, limit: int
    ) -> tuple[Sequence[User], int]:
        await self.get(org_id=org_id, group_id=group_id)
        return await self.repo.list_members(group_id, offset=offset, limit=limit)

    async def groups_of_user(
        self, *, org_id: uuid.UUID, user_id: uuid.UUID
    ) -> Sequence[tuple[UserGroup, int]]:
        """Which groups this person is in. Scoped to the caller's organization.

        Annotated ``Sequence`` and not ``list``: this class has a method called ``list``,
        so by the time the body reaches here the bare name is bound to that method and
        ``list[...]`` is an attempt to subscript a function — a ``TypeError`` at import
        time that takes the whole API down. (The ``list`` method's own annotation gets
        away with it only because its name is not bound yet while it is being defined.)
        """
        return await self.repo.groups_of_user(user_id, org_id)

    async def _assert_users_in_org(
        self, *, org_id: uuid.UUID, user_ids: Sequence[uuid.UUID]
    ) -> None:
        """Refuse to put someone from another organization into this group.

        Same rule and same reason as ``EnrollmentService._assert_users_in_org``: the
        group is scoped by ``org_id`` but nothing constrains the ids in the request
        body, and a cross-tenant membership would later expand into a cross-tenant
        enrollment. Checked here, at the write, rather than filtered at the read.
        """
        wanted = set(user_ids)
        if not wanted:
            return
        rows = await self.repo.session.execute(
            select(User.id).where(User.id.in_(wanted), User.org_id == org_id)
        )
        missing = wanted - {row[0] for row in rows.all()}
        if missing:
            raise ForbiddenError(
                "Cannot add users from another organisation: "
                + ", ".join(str(uid) for uid in sorted(missing, key=str))
            )

    async def update_members(
        self,
        *,
        org_id: uuid.UUID,
        group_id: uuid.UUID,
        add: Sequence[uuid.UUID],
        remove: Sequence[uuid.UUID],
    ) -> tuple[int, int]:
        """Apply one membership edit. Returns ``(added, removed)``.

        Additions and removals travel together because that is how the screen edits
        them: a page of ticks produces both, and splitting them into two requests would
        let one land without the other.

        An id in both lists is a contradiction the caller cannot mean, so it is refused
        rather than resolved by ordering — silently preferring one would make the result
        depend on an implementation detail nobody can see.
        """
        both = set(add) & set(remove)
        if both:
            raise ConflictError(
                "The same person cannot be added and removed in one request",
                field="add",
            )
        await self.get(org_id=org_id, group_id=group_id)
        await self._assert_users_in_org(org_id=org_id, user_ids=add)
        added = await self.repo.add_members(group_id, add)
        removed = await self.repo.remove_members(group_id, remove)
        return added, removed
