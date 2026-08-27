"""Business rules of a people group: its name, its membership, and its tenant.

A group is deliberately small — a name and a list of people — so what is worth pinning is
exactly the handful of places where "small" could still be wrong:

* the name is unique per organization, case-insensitively, like a course folder's;
* a group of another organization is a 404, never a 403 and never a silent read;
* a person from another organization cannot be added, because that membership would
  later expand into an enrollment in the wrong tenant;
* adding and removing the same person in one request is refused rather than resolved by
  order of operations, which nobody can see;
* deleting a group deletes memberships and **no training**.

No database: the repository is a mock, and the service under test is the real one.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.services.user_group_service import UserGroupService

ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
OTHER_ORG_ID = uuid.UUID("1111ffff-1111-1111-1111-111111111111")
GROUP_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
ANA = uuid.UUID("33333333-3333-3333-3333-333333333333")
BRUNO = uuid.UUID("44444444-4444-4444-4444-444444444444")
#: Belongs to `OTHER_ORG_ID`, so `_assert_users_in_org` must not find it.
OUTSIDER = uuid.UUID("55555555-5555-5555-5555-555555555555")


def _repo(*, group_org_id: uuid.UUID | None = ORG_ID, users_in_org=(ANA, BRUNO)):
    """A repository double whose session answers the one query the service runs.

    ``_assert_users_in_org`` executes ``select(User.id).where(id.in_(...), org_id==...)``
    and reads ``.all()`` as ``[(id,), ...]``. Returning a fixed set models "these are the
    people of the queried organization", which is how a request naming an outsider is
    made to look exactly like it does in production.
    """
    group = (
        SimpleNamespace(id=GROUP_ID, name="Turno de tarde", org_id=group_org_id)
        if group_org_id is not None
        else None
    )
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(all=lambda: [(uid,) for uid in users_in_org])
        )
    )
    return SimpleNamespace(
        session=session,
        get_scoped=AsyncMock(
            return_value=group if group_org_id == ORG_ID else None
        ),
        get_by_name=AsyncMock(return_value=None),
        create=AsyncMock(return_value=group),
        update=AsyncMock(return_value=group),
        delete=AsyncMock(return_value=None),
        # Both count what they were handed, like the real ones: an empty list is a
        # no-op that writes nothing and reports 0, and a fixed `1` would have hidden
        # exactly that in the test below.
        add_members=AsyncMock(side_effect=lambda _gid, ids: len(set(ids))),
        remove_members=AsyncMock(side_effect=lambda _gid, ids: len(set(ids))),
    )


@pytest.mark.asyncio
async def test_group_names_are_unique_case_insensitively() -> None:
    repo = _repo()
    repo.get_by_name = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))

    with pytest.raises(ConflictError):
        await UserGroupService(repo).create(org_id=ORG_ID, name="turno de tarde")


@pytest.mark.asyncio
async def test_renaming_onto_its_own_name_is_allowed() -> None:
    """The duplicate check must not trip over the group it is renaming."""
    repo = _repo()
    repo.get_by_name = AsyncMock(
        return_value=SimpleNamespace(id=GROUP_ID, name="Turno de tarde")
    )

    await UserGroupService(repo).update(
        org_id=ORG_ID, group_id=GROUP_ID, name="Turno de Tarde"
    )

    repo.update.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_group_of_another_organisation_is_a_404() -> None:
    """404 and not 403: a foreign group must be indistinguishable from a missing one."""
    repo = _repo(group_org_id=OTHER_ORG_ID)

    with pytest.raises(NotFoundError):
        await UserGroupService(repo).get(org_id=ORG_ID, group_id=GROUP_ID)


@pytest.mark.asyncio
async def test_membership_of_a_foreign_group_cannot_be_edited() -> None:
    repo = _repo(group_org_id=OTHER_ORG_ID)

    with pytest.raises(NotFoundError):
        await UserGroupService(repo).update_members(
            org_id=ORG_ID, group_id=GROUP_ID, add=[ANA], remove=[]
        )

    repo.add_members.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_person_from_another_organisation_cannot_be_added() -> None:
    """The cross-tenant door, closed at the write.

    A membership row pointing at a foreign user would expand into an enrollment for
    somebody the admin has no business enrolling — the very failure
    ``EnrollmentService._assert_users_in_org`` exists to stop, one table earlier.
    """
    repo = _repo(users_in_org=(ANA,))

    with pytest.raises(ForbiddenError):
        await UserGroupService(repo).update_members(
            org_id=ORG_ID, group_id=GROUP_ID, add=[ANA, OUTSIDER], remove=[]
        )

    # Nothing partial: the valid half of the request is not written either.
    repo.add_members.assert_not_awaited()


@pytest.mark.asyncio
async def test_adding_and_removing_the_same_person_is_refused() -> None:
    """Two contradictory instructions in one body. Order must not decide the winner."""
    repo = _repo()

    with pytest.raises(ConflictError):
        await UserGroupService(repo).update_members(
            org_id=ORG_ID, group_id=GROUP_ID, add=[ANA], remove=[ANA]
        )

    repo.add_members.assert_not_awaited()
    repo.remove_members.assert_not_awaited()


@pytest.mark.asyncio
async def test_removals_are_not_checked_against_the_organisation() -> None:
    """Removal is a cleanup, so it must work on a row that should not exist.

    ``_assert_users_in_org`` guards additions only. If a membership somehow points at a
    user the organization no longer owns, refusing to remove it would make the bad row
    permanent — the check would be protecting the wrong side of the door.
    """
    repo = _repo(users_in_org=())

    added, removed = await UserGroupService(repo).update_members(
        org_id=ORG_ID, group_id=GROUP_ID, add=[], remove=[OUTSIDER]
    )

    assert (added, removed) == (0, 1)
    repo.remove_members.assert_awaited_once()


@pytest.mark.asyncio
async def test_deleting_a_group_deletes_only_the_group() -> None:
    """No enrollment is touched; ``source_group_id`` is ``ON DELETE SET NULL``."""
    repo = _repo()

    await UserGroupService(repo).delete(org_id=ORG_ID, group_id=GROUP_ID)

    repo.delete.assert_awaited_once()
