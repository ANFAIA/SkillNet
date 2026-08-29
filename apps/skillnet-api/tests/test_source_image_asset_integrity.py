"""A ``source_images`` row whose file is gone says so, instead of a mute ``404``.

The same bug as the media one (``tests/test_media_asset_integrity.py``), in the other
store: ``source_images`` recorded an image extracted from a customer's document, the upload
volume was lost, and ``GET /documents/{id}/images/{id}`` swallowed the ``FileNotFoundError``
into a bare ``404`` — no log line, and no way for anyone to tell that broken state from an
image that was never extracted.

What is asserted here is what can be asserted *without a status column* on the table: the
two absences answer differently (``404`` never extracted, ``410 asset_missing`` lost), the
loss is logged at ``error`` with the path and only once per image, a row this store could
never have written is logged too but stays a ``404``, and the healthy path is untouched.
"""

from __future__ import annotations

import logging
import uuid

import pytest
from fastapi.testclient import TestClient

from src.config import settings
from src.deps.auth import current_user
from src.deps.db import get_async_session
from src.main import create_app
from src.models import UserRole
from src.routes import documents as document_routes

ORG_ID = uuid.uuid4()
DOCUMENT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()

PRESENT_HASH = "a" * 64
LOST_HASH = "b" * 64


class _FakeImage:
    """Enough of a ``SourceImage`` for the asset route and the report."""

    def __init__(self, *, content_hash: str = LOST_HASH, ext: str = "png") -> None:
        self.id = uuid.uuid4()
        self.org_id = ORG_ID
        self.document_id = DOCUMENT_ID
        self.page = 3
        self.content_hash = content_hash
        self.asset_path = f"/data/source_images/{ORG_ID}/{DOCUMENT_ID}/{content_hash}.{ext}"


class _FakeSession:
    async def commit(self) -> None:  # pragma: no cover - the route never writes
        raise AssertionError("serving an image must not write to the database")


class _FakeUser:
    id = USER_ID
    org_id = ORG_ID
    role = UserRole.EMPLOYEE


@pytest.fixture(autouse=True)
def _forget_reported(monkeypatch: pytest.MonkeyPatch):
    """The "already logged" memory is process-wide; each test starts with it empty."""
    monkeypatch.setattr(document_routes, "_reported_missing", set())


@pytest.fixture
def image_store(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """An empty source-image directory, so "the file is not there" is the default."""
    monkeypatch.setattr(settings, "SOURCE_IMAGES_DIR", str(tmp_path))
    return tmp_path / str(ORG_ID) / str(DOCUMENT_ID)


@pytest.fixture
def route_client(monkeypatch: pytest.MonkeyPatch):
    """The real app with the cookie and the database faked.

    Yields ``(client, put)`` where ``put(image)`` installs the row the route resolves to,
    and ``put(None)`` leaves the table empty.
    """
    holder: dict[str, _FakeImage | None] = {"image": None}

    class _FakeRepository:
        def __init__(self, db) -> None:  # noqa: ANN001 - the session is unused here
            self._db = db

        async def get_scoped(self, image_id, org_id, document_id):  # noqa: ANN001
            image = holder["image"]
            if image is None or org_id != ORG_ID or document_id != DOCUMENT_ID:
                return None
            return image

    monkeypatch.setattr(document_routes, "SourceImageRepository", _FakeRepository)

    app = create_app()
    app.dependency_overrides[current_user] = lambda: _FakeUser()
    app.dependency_overrides[get_async_session] = lambda: _FakeSession()

    def put(image: _FakeImage | None) -> _FakeImage | None:
        holder["image"] = image
        return image

    try:
        yield TestClient(app), put
    finally:
        app.dependency_overrides.clear()


def _url(image: _FakeImage) -> str:
    return f"/api/v1/documents/{DOCUMENT_ID}/images/{image.id}"


def test_a_present_image_is_still_served(route_client, image_store) -> None:
    client, put = route_client
    image_store.mkdir(parents=True)
    (image_store / f"{PRESENT_HASH}.png").write_bytes(b"\x89PNG-bytes")
    image = put(_FakeImage(content_hash=PRESENT_HASH))

    response = client.get(_url(image))

    assert response.status_code == 200
    assert response.content == b"\x89PNG-bytes"
    assert response.headers["content-type"] == "image/png"
    assert "immutable" in response.headers["cache-control"]


def test_never_extracted_is_a_404(route_client, image_store) -> None:
    client, put = route_client
    put(None)

    response = client.get(f"/api/v1/documents/{DOCUMENT_ID}/images/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_a_lost_file_is_a_410_that_names_itself(route_client, image_store) -> None:
    """The mute 404 this replaces could not say which of the two things had happened."""
    client, put = route_client
    image = put(_FakeImage())

    response = client.get(_url(image))

    assert response.status_code == 410
    payload = response.json()
    assert payload["code"] == "asset_missing"
    assert payload["details"] == {
        "document_id": str(DOCUMENT_ID),
        "image_id": str(image.id),
    }
    # And the sentence tells the reader what to do, naming nothing internal.
    for leak in ("/data/", "Traceback", "source_images"):
        assert leak not in payload["detail"]


def test_the_loss_is_logged_as_an_error_with_the_path(
    route_client, image_store, caplog: pytest.LogCaptureFixture
) -> None:
    """This failure used to leave no trace at all; the operator needs the path."""
    client, put = route_client
    image = put(_FakeImage())

    with caplog.at_level(logging.ERROR):
        client.get(_url(image))

    records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert records, "the inconsistency must be logged"
    message = records[0].getMessage()
    assert f"{LOST_HASH}.png" in message
    assert str(image.id) in message
    assert str(DOCUMENT_ID) in message


def test_a_lost_file_is_not_logged_again_on_every_reload(
    route_client, image_store, caplog: pytest.LogCaptureFixture
) -> None:
    """A learner reloading a lesson with a lost figure must not print fifty lines.

    Media remembers this by demoting the row; with no status column on ``source_images``
    the memory is per process, which is what this pins down.
    """
    client, put = route_client
    image = put(_FakeImage())
    assert client.get(_url(image)).status_code == 410

    caplog.clear()
    with caplog.at_level(logging.ERROR):
        assert client.get(_url(image)).status_code == 410

    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


def test_another_lost_image_is_still_reported(
    route_client, image_store, caplog: pytest.LogCaptureFixture
) -> None:
    """The silence is per image, not per process: a second loss is news."""
    client, put = route_client
    first = put(_FakeImage())
    client.get(_url(first))

    second = put(_FakeImage(content_hash="c" * 64))
    caplog.clear()
    with caplog.at_level(logging.ERROR):
        assert client.get(_url(second)).status_code == 410

    records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert records and str(second.id) in records[0].getMessage()


def test_the_memory_of_reported_losses_cannot_grow_without_end(
    route_client, image_store, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, put = route_client
    monkeypatch.setattr(document_routes, "_REPORTED_MISSING_CAP", 2)

    for _ in range(5):
        assert client.get(_url(put(_FakeImage()))).status_code == 410

    assert len(document_routes._reported_missing) <= 2


def test_a_row_this_store_could_never_have_written_stays_a_404(
    route_client, image_store, caplog: pytest.LogCaptureFixture
) -> None:
    """No path to look for, so no ``410`` — but a writer put it there, so it is logged."""
    client, put = route_client
    image = put(_FakeImage(content_hash="not-a-digest"))

    with caplog.at_level(logging.ERROR):
        response = client.get(_url(image))

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert records and str(image.id) in records[0].getMessage()


def test_an_unsupported_extension_stays_a_404(route_client, image_store) -> None:
    """The extension is allow-listed in the store, and the route must not widen it."""
    client, put = route_client
    image = put(_FakeImage(content_hash=PRESENT_HASH, ext="svg"))

    assert client.get(_url(image)).status_code == 404
