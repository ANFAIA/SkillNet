"""Admin routes for people groups: CRUD and membership.

There is deliberately **no assignment endpoint here**. Assigning training to a group is
``POST /enrollments`` with ``group_ids``, or ``POST /course-folders/{id}/assign`` with
the same field — the two entry points that already existed. A third one would be a third
place for "what does assigning mean" to drift.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from src.deps.auth import AdminUser
from src.deps.db import DBSession
from src.models.base import as_utc
from src.repositories.user_group_repo import UserGroupRepository
from src.schemas.common import PaginatedResponse
from src.schemas.user import UserRead
from src.schemas.user_group import (
    UserGroupMembersResult,
    UserGroupMembersUpdate,
    UserGroupRead,
    UserGroupWrite,
)
from src.services.user_group_service import UserGroupService

router = APIRouter(prefix="/user-groups", tags=["People groups"])
#: The one group route that hangs off the *person*. Registered by `main` alongside the
#: other collective surfaces, so it 404s in an individual workspace like the rest.
person_router = APIRouter(prefix="/users", tags=["People groups"])


def _service(db: DBSession) -> UserGroupService:
    return UserGroupService(UserGroupRepository(db))


def _read(group, count: int = 0) -> UserGroupRead:
    return UserGroupRead(
        id=group.id,
        name=group.name,
        member_count=count,
        # Both timestamps are naive UTC in the database (`TimestampMixin`, and the
        # `now()` server default on a UTC deployment), and an offset-less ISO string is
        # parsed as *local* time by `new Date()`. `CourseFolderRead` stamps only
        # `updated_at`, which leaves its `created_at` off by the browser's offset near
        # midnight; the same bug is not worth copying for symmetry.
        created_at=as_utc(group.created_at),
        updated_at=as_utc(group.updated_at),
    )


@router.get("", response_model=PaginatedResponse[UserGroupRead])
async def list_groups(
    admin: AdminUser,
    db: DBSession,
    search: Annotated[str | None, Query()] = None,
    exclude_user_id: Annotated[uuid.UUID | None, Query()] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PaginatedResponse[UserGroupRead]:
    """One page of the organization's groups, ordered by name.

    Paginated and searchable like ``GET /users`` and ``GET /courses``, and for the same
    reason: nothing bounds how many groups an organization has, and a response that
    returned all of them made every surface that reads it — the people rail, the group
    picker on an employee's record — degrade quietly as the list grew. ``search``
    matches the name case-insensitively in SQL; narrowing the page in the browser finds
    only the groups that happened to be on it.

    ``exclude_user_id`` answers "which groups is this person *not* in", the complement
    of ``GET /users/{id}/groups`` and the only list worth offering on their record.
    Like ``exclude_group_id`` on ``GET /users``, it is a filter and not an error: an
    unknown person is simply nobody's member, so every group comes back.
    """
    rows, total = await _service(db).list(
        admin.org_id,
        search=search,
        exclude_user_id=exclude_user_id,
        offset=offset,
        limit=limit,
    )
    return PaginatedResponse[UserGroupRead](
        items=[_read(group, count) for group, count in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("", response_model=UserGroupRead, status_code=201)
async def create_group(
    admin: AdminUser, db: DBSession, body: UserGroupWrite
) -> UserGroupRead:
    group = await _service(db).create(org_id=admin.org_id, name=body.name)
    await db.commit()
    return _read(group)


@router.put("/{group_id}", response_model=UserGroupRead)
async def update_group(
    admin: AdminUser, db: DBSession, group_id: uuid.UUID, body: UserGroupWrite
) -> UserGroupRead:
    service = _service(db)
    group = await service.update(org_id=admin.org_id, group_id=group_id, name=body.name)
    # Read the count back rather than answering `member_count: 0`. A rename does not empty
    # a group, and a client that seeds its cache from the mutation body instead of
    # invalidating would show exactly that. (`create_group` needs no such read: a group
    # that has just been created really does have nobody in it.)
    _rows, member_count = await service.list_members(
        org_id=admin.org_id, group_id=group_id, offset=0, limit=1
    )
    await db.commit()
    return _read(group, member_count)


@router.delete("/{group_id}", status_code=204)
async def delete_group(
    admin: AdminUser, db: DBSession, group_id: uuid.UUID
) -> Response:
    """Delete the group. Nobody is un-enrolled.

    ``enrollments.source_group_id`` is ``ON DELETE SET NULL``: the training the group
    handed out stays, and only the note of where it came from goes.
    """
    await _service(db).delete(org_id=admin.org_id, group_id=group_id)
    await db.commit()
    return Response(status_code=204)


@person_router.get("/{user_id}/groups", response_model=list[UserGroupRead])
async def groups_of_person(
    admin: AdminUser, db: DBSession, user_id: uuid.UUID
) -> list[UserGroupRead]:
    """The groups one person belongs to.

    Lives on ``/users/{id}/groups`` rather than under ``/user-groups`` because that is
    the resource being described — the person — and it is the employee record that asks.
    Membership could be edited only from the group's side until this existed, so putting
    somebody into a group meant leaving their record, finding the group and searching for
    them there.

    Writes still go through ``PUT /user-groups/{id}/members``: one door for changing
    membership, whichever screen opens it.
    """
    rows = await _service(db).groups_of_user(org_id=admin.org_id, user_id=user_id)
    return [_read(group, count) for group, count in rows]


@router.get("/{group_id}/members", response_model=PaginatedResponse[UserRead])
async def list_members(
    admin: AdminUser,
    db: DBSession,
    group_id: uuid.UUID,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PaginatedResponse[UserRead]:
    rows, total = await _service(db).list_members(
        org_id=admin.org_id, group_id=group_id, offset=offset, limit=limit
    )
    return PaginatedResponse[UserRead](
        items=[UserRead.model_validate(user) for user in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.put("/{group_id}/members", response_model=UserGroupMembersResult)
async def update_members(
    admin: AdminUser,
    db: DBSession,
    group_id: uuid.UUID,
    body: UserGroupMembersUpdate,
) -> UserGroupMembersResult:
    """Add and remove members in one transaction.

    Idempotent in both directions: adding somebody already in, or removing somebody who
    was never there, is a no-op that is reported in the counts rather than an error. The
    screen that sends this reads a paginated list, so it can be a page behind reality.
    """
    service = _service(db)
    added, removed = await service.update_members(
        org_id=admin.org_id, group_id=group_id, add=body.add, remove=body.remove
    )
    _rows, total = await service.list_members(
        org_id=admin.org_id, group_id=group_id, offset=0, limit=1
    )
    await db.commit()
    return UserGroupMembersResult(
        added_count=added, removed_count=removed, member_count=total
    )
