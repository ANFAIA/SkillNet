"""``POST /media/artifacts`` refuses what this deployment cannot generate.

The point of the gate is that the refusal is **immediate and typed**. Before it, a
deployment with no image key accepted the job, ran it for half a minute and then showed the
learner a provider's raw exception string.

The route is exercised through the real app with only its two edges faked — the session
cookie and the database — so what is under test is the wiring (status code, ``code``,
``details``) and not a mock of it.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from src.deps.auth import current_user
from src.deps.db import get_async_session
from src.main import create_app
from src.models import MediaKind, UserRole
from src.schemas.capabilities import (
    Capabilities,
    Capability,
    CapabilityReason,
    CapabilityStatus,
)
from src.services import provider_health
from src.services.media.requirements import (
    MEDIA_KIND_REQUIREMENTS,
    blocking_capability,
    ensure_kind_is_available,
)
from src.core.exceptions import CapabilityBlockedError

ORG_ID = uuid.uuid4()
COURSE_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _capabilities(**overrides: Capability) -> Capabilities:
    ready = Capability(status=CapabilityStatus.READY)
    values = {name: ready for name in Capabilities.model_fields}
    values.update(overrides)
    return Capabilities(**values)


_BLOCKED_IMAGES = Capability(
    status=CapabilityStatus.BLOCKED, reason=CapabilityReason.MISSING_API_KEY
)


# --------------------------------------------------------------------------------------
# The registry and the guard, on their own
# --------------------------------------------------------------------------------------
def test_every_media_kind_declares_its_requirements() -> None:
    """A new kind must be given a row, even an empty one, rather than defaulting to none."""
    assert set(MEDIA_KIND_REQUIREMENTS) == set(MediaKind)


def test_infographic_slides_and_video_require_images() -> None:
    for kind in (MediaKind.INFOGRAPHIC, MediaKind.SLIDES, MediaKind.VIDEO):
        assert "images" in MEDIA_KIND_REQUIREMENTS[kind], kind
    assert "images" not in MEDIA_KIND_REQUIREMENTS[MediaKind.PODCAST]


def test_every_generated_kind_requires_the_llm() -> None:
    for kind in (
        MediaKind.PODCAST,
        MediaKind.SLIDES,
        MediaKind.INFOGRAPHIC,
        MediaKind.VIDEO,
    ):
        assert "ai" in MEDIA_KIND_REQUIREMENTS[kind], kind


def test_a_degraded_capability_does_not_block() -> None:
    """DEGRADED means "works, on a lesser path" — the offline voice is still a voice."""
    caps = _capabilities(
        tts=Capability(
            status=CapabilityStatus.DEGRADED, reason=CapabilityReason.NOT_CONFIGURED
        )
    )

    assert blocking_capability(MediaKind.PODCAST, caps) is None
    ensure_kind_is_available(MediaKind.PODCAST, caps)


def test_a_blocked_capability_names_itself_in_the_error() -> None:
    caps = _capabilities(images=_BLOCKED_IMAGES)

    with pytest.raises(CapabilityBlockedError) as raised:
        ensure_kind_is_available(MediaKind.INFOGRAPHIC, caps)

    error = raised.value
    assert error.code == "capability_blocked"
    assert error.status_code == 409
    assert error.details == {
        "capability": "images",
        "reason": "missing_api_key",
        "kind": "infographic",
    }


def test_the_public_message_names_no_key_and_no_provider() -> None:
    """It reaches a learner, who can act on neither."""
    caps = _capabilities(images=_BLOCKED_IMAGES)

    with pytest.raises(CapabilityBlockedError) as raised:
        ensure_kind_is_available(MediaKind.INFOGRAPHIC, caps)

    message = raised.value.message
    for leak in ("API_KEY", "OPENROUTER", "openrouter", ".env"):
        assert leak not in message


# --------------------------------------------------------------------------------------
# The route
# --------------------------------------------------------------------------------------
class _FakeUser:
    id = USER_ID
    org_id = ORG_ID
    role = UserRole.ADMIN


class _FakeCourse:
    id = COURSE_ID
    org_id = ORG_ID
    artifact_generate_policy = "admin"


class _FakeSession:
    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class _FakeCourseRepository:
    def __init__(self, db) -> None:  # noqa: ANN001 - the session is unused here
        self._db = db

    async def get_scoped(self, course_id, org_id):  # noqa: ANN001
        return _FakeCourse()

    async def list_artifact_generator_ids(self, course_id):  # noqa: ANN001
        return []


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    """The real app, with only the session cookie and the database faked out."""
    provider_health.reset()
    from src.routes import media as media_routes

    monkeypatch.setattr(media_routes, "CourseRepository", _FakeCourseRepository)

    app = create_app()
    app.dependency_overrides[current_user] = lambda: _FakeUser()
    app.dependency_overrides[get_async_session] = lambda: _FakeSession()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        provider_health.reset()


def _body(kind: str) -> dict:
    return {"course_id": str(COURSE_ID), "kind": kind, "scope": "course"}


def test_a_blocked_kind_is_refused_with_the_typed_code(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.routes import media as media_routes

    monkeypatch.setattr(
        media_routes,
        "derive_capabilities",
        lambda: _capabilities(images=_BLOCKED_IMAGES),
    )

    response = client.post("/api/v1/media/artifacts", json=_body("infographic"))

    assert response.status_code == 409
    payload = response.json()
    assert payload["code"] == "capability_blocked"
    assert payload["field"] == "images"
    assert payload["details"] == {
        "capability": "images",
        "reason": "missing_api_key",
        "kind": "infographic",
    }


def test_a_ready_kind_is_still_accepted(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.routes import media as media_routes

    artifact_id = uuid.uuid4()

    class _Artifact:
        id = artifact_id
        status = "pending"

    async def _enqueue(db, **kwargs):  # noqa: ANN001, ANN003
        return _Artifact()

    monkeypatch.setattr(media_routes, "derive_capabilities", _capabilities)
    monkeypatch.setattr(media_routes, "enqueue_artifact", _enqueue)
    monkeypatch.setattr(media_routes, "spawn_media_job", lambda _id: None)

    response = client.post("/api/v1/media/artifacts", json=_body("infographic"))

    assert response.status_code == 202
    assert response.json()["artifact_id"] == str(artifact_id)


def test_a_kind_that_needs_nothing_is_never_refused(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mind map is assembled from the grounding bundle; no provider is involved."""
    from src.routes import media as media_routes

    artifact_id = uuid.uuid4()

    class _Artifact:
        id = artifact_id
        status = "pending"

    async def _enqueue(db, **kwargs):  # noqa: ANN001, ANN003
        return _Artifact()

    everything_blocked = Capabilities(
        **{
            name: Capability(
                status=CapabilityStatus.BLOCKED,
                reason=CapabilityReason.MISSING_API_KEY,
            )
            for name in Capabilities.model_fields
        }
    )
    monkeypatch.setattr(
        media_routes, "derive_capabilities", lambda: everything_blocked
    )
    monkeypatch.setattr(media_routes, "enqueue_artifact", _enqueue)
    monkeypatch.setattr(media_routes, "spawn_media_job", lambda _id: None)

    response = client.post("/api/v1/media/artifacts", json=_body("mindmap"))

    assert response.status_code == 202
