"""A ``done`` media artefact whose file is gone stops claiming to be ready.

The bug this pins down: ``media_artifacts`` said ``done`` with an ``asset_path``, the media
volume had been lost, and the asset route answered a bare ``404`` — for ever, to every
reader, with nothing in the log. The learner read a red "Audio no disponible" for a fault
they could neither cause nor fix, and no operator could tell that broken state from an
artefact that simply never had bytes.

So three things are asserted here: the two absences answer differently (``404`` for never
generated, ``410 asset_missing`` for lost), the row is demoted to ``error`` so every other
reader of it stops lying too, and the healthy path is untouched.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from src.config import settings
from src.deps.auth import current_user
from src.deps.db import get_async_session
from src.main import create_app
from src.models import MediaArtifactStatus, MediaKind, UserRole
from src.services.media.integrity import (
    asset_is_on_disk,
    reconcile_asset,
    record_missing_asset,
)
from src.services.media.jobs import ERROR_ASSET_MISSING

ORG_ID = uuid.uuid4()
COURSE_ID = uuid.uuid4()
NODE_ID = uuid.uuid4()
USER_ID = uuid.uuid4()

AUDIO_REF = "a" * 64
IMAGE_REF = "b" * 64


# --------------------------------------------------------------------------------------
# Doubles
# --------------------------------------------------------------------------------------
class _FakeArtifact:
    """Enough of a ``MediaArtifact`` for the schema, the route and the demotion."""

    def __init__(
        self,
        *,
        status: MediaArtifactStatus = MediaArtifactStatus.DONE,
        asset_path: str | None = None,
        spec_json: dict | None = None,
    ) -> None:
        now = datetime.now(UTC)
        self.id = uuid.uuid4()
        self.org_id = ORG_ID
        self.course_id = COURSE_ID
        self.node_id = NODE_ID
        self.kind = MediaKind.PODCAST
        self.status = status
        self.spec_json = spec_json or {}
        self.asset_path = asset_path
        self.content_hash = "deadbeef"
        self.error: str | None = None
        self.error_code: str | None = None
        self.created_at = now
        self.updated_at = now


class _FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class _FakeUser:
    id = USER_ID
    org_id = ORG_ID
    role = UserRole.EMPLOYEE


@pytest.fixture
def artifact_store(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """An empty asset directory, so "the file is not there" is the default."""
    monkeypatch.setattr(settings, "MEDIA_ASSETS_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def route_client(monkeypatch: pytest.MonkeyPatch):
    """The real app with the cookie and the database faked, plus the row it will serve.

    Yields ``(client, put)`` where ``put(artifact)`` installs the row every media read
    resolves to.
    """
    session = _FakeSession()
    holder: dict[str, _FakeArtifact | None] = {"artifact": None}

    class _FakeRepository:
        def __init__(self, db) -> None:  # noqa: ANN001 - the session is unused here
            self._db = db

        async def get_scoped(self, artifact_id, org_id):  # noqa: ANN001
            artifact = holder["artifact"]
            if artifact is None or org_id != ORG_ID:
                return None
            return artifact

    from src.routes import media as media_routes

    monkeypatch.setattr(media_routes, "MediaArtifactRepository", _FakeRepository)

    app = create_app()
    app.dependency_overrides[current_user] = lambda: _FakeUser()
    app.dependency_overrides[get_async_session] = lambda: session

    def put(artifact: _FakeArtifact) -> _FakeArtifact:
        holder["artifact"] = artifact
        return artifact

    try:
        yield TestClient(app), put
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------------------
# The reconciliation itself
# --------------------------------------------------------------------------------------
async def test_a_present_file_is_left_alone(artifact_store) -> None:
    path = artifact_store / "podcast.mp3"
    path.write_bytes(b"id3")
    artifact = _FakeArtifact(asset_path=str(path))
    session = _FakeSession()

    assert asset_is_on_disk(artifact) is True
    assert await reconcile_asset(session, artifact) is True
    assert artifact.status is MediaArtifactStatus.DONE
    assert session.commits == 0


async def test_a_done_row_with_no_file_is_demoted_to_error(artifact_store) -> None:
    artifact = _FakeArtifact(asset_path=str(artifact_store / "gone.mp3"))
    session = _FakeSession()

    assert await reconcile_asset(session, artifact) is False
    assert artifact.status is MediaArtifactStatus.ERROR
    assert artifact.error_code == ERROR_ASSET_MISSING
    # The user-facing text says what happened and what to do, and names nothing internal.
    assert artifact.error
    for leak in ("/data/", "Traceback", "media_assets"):
        assert leak not in artifact.error
    assert session.commits == 1


async def test_the_loss_is_logged_as_an_error_with_the_path(
    artifact_store, caplog: pytest.LogCaptureFixture
) -> None:
    """This failure used to leave no trace at all; the operator needs the path."""
    artifact = _FakeArtifact(asset_path=str(artifact_store / "gone.mp3"))

    with caplog.at_level(logging.ERROR):
        await record_missing_asset(_FakeSession(), artifact)

    records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert records, "the inconsistency must be logged"
    assert "gone.mp3" in records[0].getMessage()
    assert str(artifact.id) in records[0].getMessage()


async def test_an_already_recorded_loss_is_not_logged_again(
    artifact_store, caplog: pytest.LogCaptureFixture
) -> None:
    """A learner reloading the page must not print the same error fifty times."""
    artifact = _FakeArtifact(asset_path=str(artifact_store / "gone.mp3"))
    session = _FakeSession()
    await record_missing_asset(session, artifact)

    caplog.clear()
    with caplog.at_level(logging.ERROR):
        await record_missing_asset(session, artifact)

    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []
    assert session.commits == 1


async def test_the_demotion_is_undone_when_the_file_comes_back(artifact_store) -> None:
    """Restoring the media volume must not leave rows frozen in a failure that ended.

    The store is content-addressed, so a file present at that path is the same bytes the
    row was written for; there is nothing left to doubt.
    """
    path = artifact_store / "restored.mp3"
    artifact = _FakeArtifact(asset_path=str(path))
    session = _FakeSession()
    await reconcile_asset(session, artifact)
    assert artifact.status is MediaArtifactStatus.ERROR

    path.write_bytes(b"id3")
    assert await reconcile_asset(session, artifact) is True
    assert artifact.status is MediaArtifactStatus.DONE
    assert artifact.error is None
    assert artifact.error_code is None


async def test_a_real_generation_failure_is_never_resurrected(artifact_store) -> None:
    """Only this module's own demotions are reversible — an LLM failure stays failed."""
    path = artifact_store / "unrelated.mp3"
    path.write_bytes(b"id3")
    artifact = _FakeArtifact(status=MediaArtifactStatus.ERROR, asset_path=str(path))
    artifact.error_code = "llm_failed"
    session = _FakeSession()

    assert await reconcile_asset(session, artifact) is False
    assert artifact.status is MediaArtifactStatus.ERROR
    assert artifact.error_code == "llm_failed"
    assert session.commits == 0


async def test_nothing_is_reconciled_before_the_job_finishes(artifact_store) -> None:
    """A pending row promises nothing yet, and a spec-only artefact never promised bytes."""
    session = _FakeSession()

    pending = _FakeArtifact(status=MediaArtifactStatus.PENDING)
    assert await reconcile_asset(session, pending) is False
    assert pending.status is MediaArtifactStatus.PENDING

    spec_only = _FakeArtifact(asset_path=None)
    assert await reconcile_asset(session, spec_only) is False
    assert spec_only.status is MediaArtifactStatus.DONE
    assert session.commits == 0


# --------------------------------------------------------------------------------------
# The asset route
# --------------------------------------------------------------------------------------
def test_a_present_asset_is_still_served(route_client, artifact_store) -> None:
    client, put = route_client
    path = artifact_store / "ready.mp3"
    path.write_bytes(b"id3-bytes")
    artifact = put(_FakeArtifact(asset_path=str(path)))

    response = client.get(f"/api/v1/media/artifacts/{artifact.id}/asset")

    assert response.status_code == 200
    assert response.content == b"id3-bytes"
    assert response.headers["content-type"] == "audio/mpeg"
    assert artifact.status is MediaArtifactStatus.DONE


def test_serving_a_recovered_asset_heals_the_row(route_client, artifact_store) -> None:
    """The read itself is the proof, so the healing costs no extra syscall."""
    client, put = route_client
    path = artifact_store / "back.mp3"
    artifact = put(_FakeArtifact(asset_path=str(path)))

    assert client.get(f"/api/v1/media/artifacts/{artifact.id}/asset").status_code == 410
    assert artifact.status is MediaArtifactStatus.ERROR

    path.write_bytes(b"id3-again")
    response = client.get(f"/api/v1/media/artifacts/{artifact.id}/asset")

    assert response.status_code == 200
    assert artifact.status is MediaArtifactStatus.DONE
    assert artifact.error_code is None


def test_never_generated_is_a_404(route_client, artifact_store) -> None:
    client, put = route_client
    artifact = put(_FakeArtifact(asset_path=None))

    response = client.get(f"/api/v1/media/artifacts/{artifact.id}/asset")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_a_lost_file_is_a_410_that_names_itself(route_client, artifact_store) -> None:
    client, put = route_client
    artifact = put(_FakeArtifact(asset_path=str(artifact_store / "lost.mp3")))

    response = client.get(f"/api/v1/media/artifacts/{artifact.id}/asset")

    assert response.status_code == 410
    payload = response.json()
    assert payload["code"] == ERROR_ASSET_MISSING
    assert payload["details"]["artifact_id"] == str(artifact.id)
    # And the row no longer claims to be ready, so every other reader stops lying too.
    assert artifact.status is MediaArtifactStatus.ERROR
    assert artifact.error_code == ERROR_ASSET_MISSING


def test_reading_the_row_reconciles_it(route_client, artifact_store) -> None:
    """The polled status is the status the asset route will honour a moment later."""
    client, put = route_client
    artifact = put(_FakeArtifact(asset_path=str(artifact_store / "lost.mp3")))

    response = client.get(f"/api/v1/media/artifacts/{artifact.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == MediaArtifactStatus.ERROR.value
    assert payload["error_code"] == ERROR_ASSET_MISSING
    # And nothing in the payload still announces bytes that are not there.
    assert payload["asset_ref"] is None
    assert payload["has_asset"] is False


def test_a_lost_narration_clip_demotes_the_row(route_client, artifact_store) -> None:
    """The per-slide audio is what a Video Overview cannot be played without."""
    client, put = route_client
    artifact = put(
        _FakeArtifact(
            spec_json={"slides": [{"audio_ref": AUDIO_REF, "image_ref": IMAGE_REF}]}
        )
    )

    response = client.get(f"/api/v1/media/artifacts/{artifact.id}/asset/{AUDIO_REF}")

    assert response.status_code == 410
    assert response.json()["code"] == ERROR_ASSET_MISSING
    assert response.json()["details"]["ref"] == AUDIO_REF
    assert artifact.status is MediaArtifactStatus.ERROR


def test_a_lost_illustration_does_not_fail_the_artefact(
    route_client, artifact_store
) -> None:
    """A deck whose picture is gone is still a deck: the viewer draws its own blocks."""
    client, put = route_client
    artifact = put(
        _FakeArtifact(
            spec_json={"slides": [{"audio_ref": AUDIO_REF, "image_ref": IMAGE_REF}]}
        )
    )

    response = client.get(f"/api/v1/media/artifacts/{artifact.id}/asset/{IMAGE_REF}")

    assert response.status_code == 404
    assert artifact.status is MediaArtifactStatus.DONE
    assert artifact.error_code is None
