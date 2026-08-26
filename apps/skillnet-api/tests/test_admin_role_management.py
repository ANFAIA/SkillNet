"""Promoting and demoting administrators, and the two things that must never happen:
an organization left with no administrator, and an admin reaching into another org.

No DB — the repository is a fake that answers `count_admins` from an in-memory list,
so the guard is exercised for real while the SQL is not.
"""

import uuid
from types import SimpleNamespace

import pytest

from src.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from src.models import UserRole
from src.services.user_service import UserService


class FakeUserRepo:
    def __init__(self, users: list) -> None:
        self.users = users
        self.updates: list[dict] = []
        self.created: list[dict] = []

    async def get_by_id(self, user_id):
        return next((u for u in self.users if u.id == user_id), None)

    async def get_by_email(self, org_id, email):
        return next(
            (u for u in self.users if u.org_id == org_id and u.email == email), None
        )

    async def count_admins(self, org_id, *, exclude_user_id=None):
        return sum(
            1
            for u in self.users
            if u.org_id == org_id
            and u.role is UserRole.ADMIN
            and u.is_active
            and u.id != exclude_user_id
        )

    async def create(self, **kwargs):
        self.created.append(dict(kwargs))
        user = SimpleNamespace(id=uuid.uuid4(), **kwargs)
        self.users.append(user)
        return user

    async def update(self, obj, **kwargs):
        self.updates.append(dict(kwargs))
        for key, value in kwargs.items():
            setattr(obj, key, value)
        return obj


def make_user(org_id, role=UserRole.EMPLOYEE, *, is_active=True, email=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        org_id=org_id,
        email=email or f"{uuid.uuid4().hex[:6]}@acme.dev",
        full_name="Someone",
        role=role,
        is_active=is_active,
    )


def make_service(users):
    repo = FakeUserRepo(users)
    return UserService(repo), repo  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# A2 — inviting another administrator
# ---------------------------------------------------------------------------


async def test_an_admin_can_create_another_admin():
    org = uuid.uuid4()
    service, repo = make_service([make_user(org, UserRole.ADMIN)])

    user, temporary_password = await service.create_employee(
        org_id=org, email="new.admin@acme.dev", full_name="New Admin", role="admin"
    )

    assert user.role is UserRole.ADMIN
    assert repo.created[0]["org_id"] == org, "always the caller's own organization"
    assert temporary_password, "the admin has to be able to hand over a password"


async def test_creating_a_member_defaults_to_employee():
    org = uuid.uuid4()
    service, _ = make_service([make_user(org, UserRole.ADMIN)])

    user, _ = await service.create_employee(
        org_id=org, email="learner@acme.dev", full_name="Learner"
    )

    assert user.role is UserRole.EMPLOYEE


async def test_an_unknown_role_is_rejected():
    org = uuid.uuid4()
    service, repo = make_service([])

    with pytest.raises(ValidationError):
        await service.create_employee(
            org_id=org, email="x@acme.dev", full_name="X", role="superadmin"
        )
    assert repo.created == []


# ---------------------------------------------------------------------------
# A3 — changing an existing member's role
# ---------------------------------------------------------------------------


async def test_promoting_an_employee_to_admin():
    org = uuid.uuid4()
    admin = make_user(org, UserRole.ADMIN)
    employee = make_user(org)
    service, _ = make_service([admin, employee])

    updated = await service.update_user(
        user_id=employee.id, org_id=org, actor_id=admin.id, role="admin"
    )

    assert updated.role is UserRole.ADMIN


async def test_demoting_an_admin_while_another_one_remains():
    org = uuid.uuid4()
    keeper = make_user(org, UserRole.ADMIN)
    demoted = make_user(org, UserRole.ADMIN)
    service, _ = make_service([keeper, demoted])

    updated = await service.update_user(
        user_id=demoted.id, org_id=org, actor_id=keeper.id, role="employee"
    )

    assert updated.role is UserRole.EMPLOYEE


async def test_only_the_two_known_roles_are_accepted():
    org = uuid.uuid4()
    admin = make_user(org, UserRole.ADMIN)
    employee = make_user(org)
    service, repo = make_service([admin, employee])

    with pytest.raises(ValidationError):
        await service.update_user(
            user_id=employee.id, org_id=org, actor_id=admin.id, role="owner"
        )
    assert repo.updates == []


# ---------------------------------------------------------------------------
# The last-admin safeguard
# ---------------------------------------------------------------------------


async def test_the_last_admin_cannot_be_demoted():
    org = uuid.uuid4()
    only_admin = make_user(org, UserRole.ADMIN)
    service, repo = make_service([only_admin, make_user(org)])

    with pytest.raises(ForbiddenError):
        await service.update_user(
            user_id=only_admin.id, org_id=org, actor_id=only_admin.id, role="employee"
        )
    assert repo.updates == []
    assert only_admin.role is UserRole.ADMIN


async def test_the_last_admin_cannot_demote_themselves_even_by_another_admins_hand():
    """There is no other admin to act, but the guard does not depend on who asks."""
    org = uuid.uuid4()
    only_admin = make_user(org, UserRole.ADMIN)
    service, repo = make_service([only_admin])

    with pytest.raises(ForbiddenError):
        await service.update_user(
            user_id=only_admin.id, org_id=org, actor_id=None, role="employee"
        )
    assert repo.updates == []


async def test_the_last_admin_cannot_be_deactivated_either():
    """The other route to the same locked-out organization."""
    org = uuid.uuid4()
    only_admin = make_user(org, UserRole.ADMIN)
    service, repo = make_service([only_admin])

    with pytest.raises(ForbiddenError):
        await service.update_user(
            user_id=only_admin.id, org_id=org, actor_id=only_admin.id, is_active=False
        )
    assert repo.updates == []
    assert only_admin.is_active is True


async def test_a_deactivated_admin_does_not_count_as_cover():
    org = uuid.uuid4()
    active_admin = make_user(org, UserRole.ADMIN)
    dormant_admin = make_user(org, UserRole.ADMIN, is_active=False)
    service, _ = make_service([active_admin, dormant_admin])

    with pytest.raises(ForbiddenError):
        await service.update_user(
            user_id=active_admin.id, org_id=org, actor_id=active_admin.id, role="employee"
        )


async def test_the_last_admin_can_still_be_renamed():
    """The guard is about losing the role, not about touching the row."""
    org = uuid.uuid4()
    only_admin = make_user(org, UserRole.ADMIN)
    service, _ = make_service([only_admin])

    updated = await service.update_user(
        user_id=only_admin.id, org_id=org, actor_id=only_admin.id, full_name="Renamed"
    )
    assert updated.full_name == "Renamed"


async def test_an_admin_of_another_org_does_not_hold_this_org_open():
    org = uuid.uuid4()
    other_org = uuid.uuid4()
    only_admin = make_user(org, UserRole.ADMIN)
    service, _ = make_service([only_admin, make_user(other_org, UserRole.ADMIN)])

    with pytest.raises(ForbiddenError):
        await service.update_user(
            user_id=only_admin.id, org_id=org, actor_id=only_admin.id, role="employee"
        )


# ---------------------------------------------------------------------------
# Cross-organization isolation
# ---------------------------------------------------------------------------


async def test_an_admin_cannot_change_the_role_of_a_user_in_another_org():
    org = uuid.uuid4()
    other_org = uuid.uuid4()
    admin = make_user(org, UserRole.ADMIN)
    stranger = make_user(other_org)
    service, repo = make_service([admin, stranger, make_user(other_org, UserRole.ADMIN)])

    with pytest.raises(NotFoundError):
        await service.update_user(
            user_id=stranger.id, org_id=org, actor_id=admin.id, role="admin"
        )
    assert repo.updates == []
    assert stranger.role is UserRole.EMPLOYEE


async def test_an_admin_cannot_read_a_user_in_another_org():
    org = uuid.uuid4()
    other_org = uuid.uuid4()
    stranger = make_user(other_org)
    service, _ = make_service([stranger])

    with pytest.raises(NotFoundError):
        await service.get_user(stranger.id, org)


async def test_an_admin_cannot_deactivate_a_user_in_another_org():
    org = uuid.uuid4()
    other_org = uuid.uuid4()
    stranger = make_user(other_org, UserRole.ADMIN)
    service, repo = make_service([stranger])

    with pytest.raises(NotFoundError):
        await service.update_user(
            user_id=stranger.id, org_id=org, actor_id=uuid.uuid4(), is_active=False
        )
    assert repo.updates == []
    assert stranger.is_active is True


async def test_an_admin_cannot_reset_the_password_of_a_user_in_another_org():
    org = uuid.uuid4()
    other_org = uuid.uuid4()
    stranger = make_user(other_org)
    service, repo = make_service([stranger])

    with pytest.raises(NotFoundError):
        await service.reset_password(
            user_id=stranger.id,
            org_id=org,
            admin_id=uuid.uuid4(),
            new_password="whatever-123",
        )
    assert repo.updates == []
