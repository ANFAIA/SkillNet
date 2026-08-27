"""No 500 leaves this API as plain text.

The regression this locks down is not the crash itself, it is what the crash *looked
like*. With no handler for `Exception`, Starlette answers `text/plain: Internal Server
Error`; `apps/skillnet-web/src/api/client.ts` tries to read the `{detail, code}` envelope
out of that body, fails, and shows the user "Unknown error". A `MissingGreenlet` on the
first `PUT /courses/{id}` therefore reached the operator as four words carrying no
information at all.

So the assertion is about the envelope and the content type, and it goes through the real
app (`create_app`) rather than calling the handler directly, because the thing that broke
was the wiring: the handler existing but not being registered would pass a direct call.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.core.exceptions import ConflictError
from src.main import create_app


@pytest.fixture
def client() -> TestClient:
    """The real app plus two routes that fail on purpose.

    `create_app()` builds a fresh instance, so the extra routes are local to the test.
    `raise_server_exceptions=False` is required: a handler registered for `Exception`
    lands on Starlette's `ServerErrorMiddleware`, which re-raises after sending the
    response, and the default TestClient would surface that instead of the response the
    browser actually gets.
    """
    app = create_app()

    @app.get("/api/v1/_test/boom")
    async def _boom() -> None:
        raise RuntimeError("greenlet_spawn has not been called; secret=hunter2")

    @app.get("/api/v1/_test/conflict")
    async def _conflict() -> None:
        raise ConflictError("Only archived courses can be unarchived", field="status")

    return TestClient(app, raise_server_exceptions=False)


def test_an_unhandled_exception_answers_json_not_plain_text(client: TestClient) -> None:
    response = client.get("/api/v1/_test/boom")

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    # The same three keys `app_error_handler` produces, so the SPA reads one shape.
    assert body == {
        "detail": "Internal server error",
        "code": "INTERNAL_ERROR",
        "field": None,
    }


def test_the_generic_500_leaks_nothing_from_the_exception(client: TestClient) -> None:
    """The message crosses the trust boundary; the traceback goes to the log instead."""
    raw = client.get("/api/v1/_test/boom").text

    for leak in ("greenlet_spawn", "hunter2", "RuntimeError", "Traceback"):
        assert leak not in raw


def test_a_typed_app_error_is_not_swallowed_by_the_generic_handler(
    client: TestClient,
) -> None:
    """Registration order matters: `AppError` still wins over `Exception`."""
    response = client.get("/api/v1/_test/conflict")

    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT"
    assert response.json()["field"] == "status"
