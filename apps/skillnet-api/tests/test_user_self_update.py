"""``PUT /users/me`` and the accessibility settings it persists.

No DB and no network: the repository is a fake that records what the service
asked it to write.

Why this file exists: ``users.accessibility`` had a client-side field and no
server-side one, so the Settings screen could submit the four reading settings
of question 5, get a ``200`` back and change nothing (pydantic's default
``extra='ignore'`` dropped the key without a ``422``). ``short_blocks`` feeds
``effective_density`` and therefore the ``cache_key`` (§3.1), so a silently
ignored setting is not cosmetic: the learner keeps getting the long-block
bucket forever. These tests pin the whole path — schema, service, route.
"""

import uuid
from types import SimpleNamespace

import pytest
from pydantic import ValidationError as PydanticValidationError

from src.models import LearningProfile
from src.routes.users import update_me
from src.schemas.onboarding import ACCESSIBILITY_KEYS
from src.schemas.user import UserSelfUpdate
from src.services.user_service import UserService

ALL_OFF = {key: False for key in ACCESSIBILITY_KEYS}


class FakeUserRepo:
    """Mirrors ``BaseRepository.update``: setattr + flush, nothing else."""

    def __init__(self) -> None:
        self.updates: list[dict] = []

    async def update(self, obj, **kwargs):
        self.updates.append(dict(kwargs))
        for key, value in kwargs.items():
            setattr(obj, key, value)
        return obj


def make_user(**overrides):
    base = dict(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        full_name="Ada",
        learning_profile=LearningProfile.STANDARD,
        accessibility={},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def make_service() -> tuple[UserService, FakeUserRepo]:
    repo = FakeUserRepo()
    return UserService(repo), repo  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Schema: the request body has to *accept* the field, with the wizard's rules
# ---------------------------------------------------------------------------


def test_self_update_accepts_the_four_reading_settings():
    body = UserSelfUpdate.model_validate({"accessibility": {"short_blocks": True}})
    assert body.accessibility is not None
    assert body.accessibility.model_dump() == {**ALL_OFF, "short_blocks": True}


def test_self_update_rejects_an_unknown_accessibility_flag():
    """Same ``extra='forbid'`` as ``POST /onboarding``: no unknown flag lands in
    the jsonb column through the Settings door either."""
    with pytest.raises(PydanticValidationError):
        UserSelfUpdate.model_validate({"accessibility": {"audio_first": True}})


def test_self_update_rejects_a_neurotype_label():
    """Art. 9 data has no field on any door (§3.3)."""
    with pytest.raises(PydanticValidationError):
        UserSelfUpdate.model_validate({"accessibility": {"dyslexia": True}})


def test_self_update_accessibility_defaults_to_none_not_empty():
    """Absent must mean "don't touch", not "clear everything"."""
    assert UserSelfUpdate().accessibility is None


# ---------------------------------------------------------------------------
# Service: the field is actually written
# ---------------------------------------------------------------------------


async def test_update_self_persists_accessibility():
    service, repo = make_service()
    user = make_user()

    updated = await service.update_self(
        user=user, accessibility={**ALL_OFF, "short_blocks": True}
    )

    assert updated.accessibility == {**ALL_OFF, "short_blocks": True}
    assert repo.updates == [{"accessibility": {**ALL_OFF, "short_blocks": True}}]


async def test_update_self_replaces_accessibility_instead_of_merging():
    """An unchecked box has to be able to turn a stored ``true`` back off."""
    service, _ = make_service()
    user = make_user(accessibility={"short_blocks": True, "high_contrast": True})

    updated = await service.update_self(user=user, accessibility=ALL_OFF)

    assert updated.accessibility == ALL_OFF


async def test_update_self_leaves_accessibility_alone_when_absent():
    service, repo = make_service()
    user = make_user(accessibility={"short_blocks": True})

    updated = await service.update_self(user=user, full_name="Grace")

    assert updated.accessibility == {"short_blocks": True}
    assert repo.updates == [{"full_name": "Grace"}]


async def test_update_self_normalizes_to_plain_booleans():
    """The jsonb column holds booleans whichever door wrote it — the onboarding
    path does the same coercion (``complete_onboarding``)."""
    service, _ = make_service()
    user = make_user()

    updated = await service.update_self(user=user, accessibility={"extra_time": 1})

    assert updated.accessibility == {"extra_time": True}
    assert updated.accessibility["extra_time"] is True


async def test_update_self_writes_name_profile_and_accessibility_in_one_update():
    service, repo = make_service()
    user = make_user()

    await service.update_self(
        user=user,
        full_name="Grace",
        learning_profile="focus",
        accessibility={**ALL_OFF, "reduce_motion": True},
    )

    assert repo.updates == [
        {
            "full_name": "Grace",
            "learning_profile": LearningProfile.FOCUS,
            "accessibility": {**ALL_OFF, "reduce_motion": True},
        }
    ]


# ---------------------------------------------------------------------------
# Route: the body reaches the service (the wiring is where it was lost)
# ---------------------------------------------------------------------------


class RecordingService:
    def __init__(self, user) -> None:
        self.user = user
        self.calls: list[dict] = []

    async def update_self(self, **kwargs):
        self.calls.append(kwargs)
        return self.user


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


async def test_update_me_route_forwards_accessibility_to_the_service(monkeypatch):
    user = make_user(
        email="ada@test.dev",
        role="employee",
        is_active=True,
        is_superuser=False,
        is_verified=False,
        hired_at=None,
    )
    service = RecordingService(user)
    monkeypatch.setattr("src.routes.users._service", lambda db: service)
    session = FakeSession()

    body = UserSelfUpdate.model_validate({"accessibility": {"short_blocks": True}})
    await update_me(user=user, db=session, body=body)  # type: ignore[arg-type]

    assert session.commits == 1
    assert service.calls == [
        {
            "user": user,
            "full_name": None,
            "learning_profile": None,
            "accessibility": {**ALL_OFF, "short_blocks": True},
        }
    ]


async def test_update_me_route_sends_none_when_accessibility_is_absent(monkeypatch):
    user = make_user(
        email="ada@test.dev",
        role="employee",
        is_active=True,
        is_superuser=False,
        is_verified=False,
        hired_at=None,
    )
    service = RecordingService(user)
    monkeypatch.setattr("src.routes.users._service", lambda db: service)

    await update_me(  # type: ignore[arg-type]
        user=user, db=FakeSession(), body=UserSelfUpdate(full_name="Grace")
    )

    assert service.calls[0]["accessibility"] is None
