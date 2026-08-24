"""Self-service account endpoints added alongside the redesigned dashboards:
``POST /users/me/change-password``, ``PUT /users/me/email`` and
``DELETE /users/me``.

No DB and no network: the repository is a fake that records what the service
asked it to write, same pattern as ``test_user_self_update.py``. Password
hashing is real (``PasswordHelper``) so the verify-current-password path is
tested for real, not assumed.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi_users.password import PasswordHelper

from src.core.exceptions import ConflictError, ValidationError
from src.deps.auth import require_individual_workspace
from src.models import WorkspaceMode
from src.routes.users import change_email, change_password, delete_account
from src.schemas.user import ChangeEmailRequest, ChangePasswordRequest, DeleteAccountRequest
from src.services.user_service import UserService

_password_helper = PasswordHelper()


class FakeUserRepo:
    """Mirrors ``BaseRepository.update``/``get_by_email``."""

    def __init__(self, *, existing_emails: dict | None = None) -> None:
        self.updates: list[dict] = []
        self._existing_emails = existing_emails or {}

    async def update(self, obj, **kwargs):
        self.updates.append(dict(kwargs))
        for key, value in kwargs.items():
            setattr(obj, key, value)
        return obj

    async def get_by_email(self, org_id, email):
        return self._existing_emails.get(email)


def make_user(**overrides):
    base = dict(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        email="ada@test.dev",
        full_name="Ada",
        hashed_password=_password_helper.hash("correct-horse"),
        is_active=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def make_service(**repo_kwargs) -> tuple[UserService, FakeUserRepo]:
    repo = FakeUserRepo(**repo_kwargs)
    return UserService(repo), repo  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# change_own_password
# ---------------------------------------------------------------------------


async def test_change_own_password_rejects_wrong_current_password():
    service, repo = make_service()
    user = make_user()

    with pytest.raises(ValidationError):
        await service.change_own_password(
            user=user, current_password="wrong", new_password="new-password-123"
        )
    assert repo.updates == []


async def test_change_own_password_updates_the_hash():
    service, repo = make_service()
    user = make_user()
    old_hash = user.hashed_password

    await service.change_own_password(
        user=user, current_password="correct-horse", new_password="new-password-123"
    )

    assert repo.updates == [{"hashed_password": user.hashed_password}]
    assert user.hashed_password != old_hash
    # The new password actually verifies against the newly stored hash.
    verified, _ = _password_helper.verify_and_update(
        "new-password-123", user.hashed_password
    )
    assert verified


# ---------------------------------------------------------------------------
# change_own_email
# ---------------------------------------------------------------------------


async def test_change_own_email_rejects_wrong_password():
    service, repo = make_service()
    user = make_user()

    with pytest.raises(ValidationError):
        await service.change_own_email(
            user=user, org_id=user.org_id, new_email="new@test.dev", current_password="wrong"
        )
    assert repo.updates == []


async def test_change_own_email_rejects_an_email_already_in_the_org():
    other = make_user(email="taken@test.dev")
    service, _ = make_service(existing_emails={"taken@test.dev": other})
    user = make_user()

    with pytest.raises(ConflictError):
        await service.change_own_email(
            user=user,
            org_id=user.org_id,
            new_email="taken@test.dev",
            current_password="correct-horse",
        )


async def test_change_own_email_allows_keeping_the_same_email():
    """Submitting the unchanged email must not trip the "already exists" check
    against your own row."""
    service, repo = make_service(existing_emails={})
    user = make_user(email="ada@test.dev")

    updated = await service.change_own_email(
        user=user,
        org_id=user.org_id,
        new_email="ada@test.dev",
        current_password="correct-horse",
    )
    assert updated.email == "ada@test.dev"


async def test_change_own_email_updates_the_email():
    service, repo = make_service()
    user = make_user()

    updated = await service.change_own_email(
        user=user,
        org_id=user.org_id,
        new_email="new@test.dev",
        current_password="correct-horse",
    )

    assert updated.email == "new@test.dev"
    assert repo.updates == [{"email": "new@test.dev"}]


# ---------------------------------------------------------------------------
# delete_own_account
# ---------------------------------------------------------------------------


async def test_delete_own_account_rejects_wrong_password():
    service, repo = make_service()
    user = make_user()

    with pytest.raises(ValidationError):
        await service.delete_own_account(user=user, current_password="wrong")
    assert repo.updates == []
    assert user.is_active is True


async def test_delete_own_account_deactivates_and_scrambles_email():
    service, repo = make_service()
    user = make_user()
    original_id = user.id

    await service.delete_own_account(user=user, current_password="correct-horse")

    assert user.is_active is False
    assert user.email == f"deleted-{original_id}@deleted.local"
    assert repo.updates == [
        {"is_active": False, "email": f"deleted-{original_id}@deleted.local"}
    ]


# ---------------------------------------------------------------------------
# require_individual_workspace: the gate on DELETE /users/me
# ---------------------------------------------------------------------------


class FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class FakeDB:
    def __init__(self, workspace_mode):
        self._workspace_mode = workspace_mode

    async def execute(self, _query):
        return FakeScalarResult(self._workspace_mode)


async def test_require_individual_workspace_allows_individual():
    user = make_user()
    await require_individual_workspace(user, FakeDB(WorkspaceMode.INDIVIDUAL))  # type: ignore[arg-type]


async def test_require_individual_workspace_blocks_organization():
    from src.core.exceptions import AppError

    user = make_user()
    with pytest.raises(AppError):
        await require_individual_workspace(user, FakeDB(WorkspaceMode.ORGANIZATION))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Routes: the body reaches the service and the transaction commits
# ---------------------------------------------------------------------------


class RecordingService:
    def __init__(self, user) -> None:
        self.user = user
        self.calls: list[tuple[str, dict]] = []

    async def change_own_password(self, **kwargs):
        self.calls.append(("change_own_password", kwargs))

    async def change_own_email(self, **kwargs):
        self.calls.append(("change_own_email", kwargs))
        return self.user

    async def delete_own_account(self, **kwargs):
        self.calls.append(("delete_own_account", kwargs))


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


async def test_change_password_route_forwards_to_the_service(monkeypatch):
    user = make_user(role="employee", is_superuser=False, is_verified=False, hired_at=None)
    service = RecordingService(user)
    monkeypatch.setattr("src.routes.users._service", lambda db: service)
    session = FakeSession()

    body = ChangePasswordRequest(current_password="old", new_password="new-password-123")
    result = await change_password(user=user, db=session, body=body)  # type: ignore[arg-type]

    assert result == {"ok": True}
    assert session.commits == 1
    assert service.calls == [
        (
            "change_own_password",
            {"user": user, "current_password": "old", "new_password": "new-password-123"},
        )
    ]


async def test_change_email_route_forwards_to_the_service(monkeypatch):
    user = make_user(
        role="employee",
        is_superuser=False,
        is_verified=False,
        hired_at=None,
        learning_profile="standard",
        accessibility={},
    )
    service = RecordingService(user)
    monkeypatch.setattr("src.routes.users._service", lambda db: service)
    session = FakeSession()

    body = ChangeEmailRequest(new_email="new@test.dev", current_password="old")
    await change_email(user=user, db=session, body=body)  # type: ignore[arg-type]

    assert session.commits == 1
    assert service.calls == [
        (
            "change_own_email",
            {
                "user": user,
                "org_id": user.org_id,
                "new_email": "new@test.dev",
                "current_password": "old",
            },
        )
    ]


async def test_delete_account_route_forwards_to_the_service(monkeypatch):
    user = make_user(role="employee", is_superuser=False, is_verified=False, hired_at=None)
    service = RecordingService(user)
    monkeypatch.setattr("src.routes.users._service", lambda db: service)
    session = FakeSession()

    body = DeleteAccountRequest(current_password="old")
    result = await delete_account(user=user, db=session, body=body, _mode=None)  # type: ignore[arg-type]

    assert result == {"ok": True}
    assert session.commits == 1
    assert service.calls == [
        ("delete_own_account", {"user": user, "current_password": "old"})
    ]
