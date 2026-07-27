"""The §10.1 truth table, over every v2 path, with no database and no network.

``tests/integration/test_v1_regression.py`` proves the same thing with real auth and a
real Postgres. This file proves it **in CI**, which is where it matters: the promise of
the flag is what lets this branch merge into a running product, and a promise that is
only checked when somebody remembers to start Docker is not checked.

It works without a database because of the order FastAPI solves dependencies in:
router-level ``dependencies=[...]`` are inserted at position 0 of the dependant tree
(``APIRoute.__init__``), so ``require_dynamic_courses`` runs **before**
``current_user`` and before ``get_async_session``. With the flag off, the request
therefore never reaches auth, let alone SQL — which is also exactly why a ``404`` here is
indistinguishable from a route that was never deployed.

| mode     | admin surface | employee surface |
|----------|---------------|------------------|
| `off`    | 404           | 404              |
| `shadow` | reached       | 404              |
| `on`     | reached       | reached          |

"Reached" is asserted as *not* ``404``: without a session cookie the next thing that
happens is a ``401``, and that is the proof the guard let the request through.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from src.config import settings
from src.main import create_app

PREFIX = "/api/v1"

COURSE_ID = uuid.uuid4()
NODE_ID = uuid.uuid4()
RENDER_ID = uuid.uuid4()
PROBE_ID = uuid.uuid4()

#: (method, path, body) for every admin-surface path of §11.1. Enumerated by hand
#: rather than derived from the OpenAPI schema: a path that disappears from the app has
#: to make this list *wrong*, not make the loop shorter.
ADMIN_SURFACE: tuple[tuple[str, str, dict | None], ...] = (
    ("POST", f"/courses/{COURSE_ID}/schema/propose", {"intent_density": 3}),
    ("GET", f"/courses/{COURSE_ID}/schema", None),
    ("PUT", f"/courses/{COURSE_ID}/schema", {"nodes": []}),
    ("POST", f"/courses/{COURSE_ID}/schema/validate", None),
    ("POST", f"/courses/{COURSE_ID}/schema/unvalidate", None),
    ("POST", f"/courses/{COURSE_ID}/schema/nodes/{NODE_ID}/review", None),
)

#: Every employee-surface path of §11.2 and §11.3, plus click-to-explain (§8.4).
EMPLOYEE_SURFACE: tuple[tuple[str, str, dict | None], ...] = (
    ("GET", "/onboarding", None),
    ("POST", "/onboarding", {"role_title": "Cajero"}),
    ("POST", "/onboarding/skip", None),
    ("GET", "/users/me/learner-profile", None),
    ("PATCH", "/users/me/learner-profile", {"preset": "focus"}),
    ("DELETE", "/users/me/learner-profile", None),
    ("GET", f"/courses/{COURSE_ID}/nodes", None),
    ("POST", f"/nodes/{NODE_ID}/probe", None),
    (
        "POST",
        f"/nodes/{NODE_ID}/probe/answer",
        {"probe_id": str(PROBE_ID), "item_id": "a", "answer": {"selected": 0}},
    ),
    ("POST", f"/nodes/{NODE_ID}/render", {"force": False}),
    ("GET", f"/nodes/{NODE_ID}/render", None),
    ("GET", f"/nodes/{NODE_ID}/renders", None),
    ("GET", f"/nodes/{NODE_ID}/render/stream?request_id=abc", None),
    (
        "POST",
        f"/nodes/{NODE_ID}/answer",
        {"render_id": str(RENDER_ID), "item_id": "q1", "answer": {"selected": 0}},
    ),
    ("POST", f"/nodes/{NODE_ID}/hint", {"render_id": str(RENDER_ID), "item_id": "q1"}),
    ("POST", f"/nodes/{NODE_ID}/feedback", {"difficulty": "ok"}),
    ("POST", f"/nodes/{NODE_ID}/events", {"events": []}),
    ("POST", f"/nodes/{NODE_ID}/waive", {"reason": "la he visto trabajar"}),
    ("POST", "/explain", {"term": "descuadre", "context": "el descuadre de caja"}),
)

#: The v1 paths that must keep answering whatever the flag says. ``401`` is the right
#: answer to an unauthenticated call; the point is that it is not ``404``.
V1_SURFACE: tuple[tuple[str, str], ...] = (
    ("GET", "/courses"),
    ("GET", f"/courses/{COURSE_ID}"),
    ("POST", f"/courses/{COURSE_ID}/generate"),
    ("POST", f"/courses/{COURSE_ID}/publish"),
    ("GET", "/documents"),
    ("GET", "/enrollments"),
    ("GET", "/users/me"),
    ("GET", "/users/me/skills"),
    ("GET", "/stats"),
    ("GET", f"/generation-jobs/{uuid.uuid4()}"),
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    """No ``with`` block on purpose: entering it would run the app lifespan, which
    migrates and bootstraps a database this test does not need and does not have."""
    return TestClient(create_app(), raise_server_exceptions=False)


def _call(client: TestClient, method: str, path: str, body: dict | None):
    return client.request(
        method, f"{PREFIX}{path}", **({"json": body} if body is not None else {})
    )


@pytest.mark.parametrize(("method", "path", "body"), ADMIN_SURFACE + EMPLOYEE_SURFACE)
def test_the_flag_off_makes_the_whole_v2_surface_a_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, method: str, path: str, body
) -> None:
    monkeypatch.setattr(settings, "DYNAMIC_COURSES_MODE", "off")
    response = _call(client, method, path, body)
    assert response.status_code == 404, response.text
    assert response.json()["code"] == "NOT_FOUND"


@pytest.mark.parametrize(("method", "path", "body"), ADMIN_SURFACE)
def test_shadow_reaches_the_admin_surface(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, method: str, path: str, body
) -> None:
    monkeypatch.setattr(settings, "DYNAMIC_COURSES_MODE", "shadow")
    response = _call(client, method, path, body)
    # 401: the guard passed and the request got as far as authentication.
    assert response.status_code == 401, response.text


@pytest.mark.parametrize(("method", "path", "body"), EMPLOYEE_SURFACE)
def test_shadow_still_hides_the_employee_surface(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, method: str, path: str, body
) -> None:
    """The mode the internal demo runs in: the creator works with real data and no
    learner can reach anything."""
    monkeypatch.setattr(settings, "DYNAMIC_COURSES_MODE", "shadow")
    response = _call(client, method, path, body)
    assert response.status_code == 404, response.text


@pytest.mark.parametrize(
    ("method", "path", "body"), ADMIN_SURFACE + EMPLOYEE_SURFACE
)
def test_on_reaches_every_v2_route(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, method: str, path: str, body
) -> None:
    monkeypatch.setattr(settings, "DYNAMIC_COURSES_MODE", "on")
    response = _call(client, method, path, body)
    assert response.status_code == 401, response.text


@pytest.mark.parametrize("mode", ["off", "shadow", "on"])
@pytest.mark.parametrize(("method", "path"), V1_SURFACE)
def test_the_v1_surface_answers_whatever_the_flag_says(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, mode: str, method: str, path: str
) -> None:
    """No v2 router shadows a v1 path, in any mode.

    ``/courses`` in particular is served by three routers now (v1 courses, the schema
    surface, the node list), and FastAPI matches in registration order — so this is the
    test that would catch a v2 path template swallowing a v1 one.
    """
    monkeypatch.setattr(settings, "DYNAMIC_COURSES_MODE", mode)
    response = client.request(method, f"{PREFIX}{path}")
    assert response.status_code == 401, response.text


@pytest.mark.parametrize("mode", ["off", "shadow", "on"])
def test_health_publishes_the_flag_and_needs_no_auth(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    """§10.1: ``GET /health`` is the only place the flag is exposed, and the client
    reads it once at startup. Mounted at the app root *and* under the prefix, because
    the Docker healthcheck uses the root one."""
    monkeypatch.setattr(settings, "DYNAMIC_COURSES_MODE", mode)
    for path in ("/health", f"{PREFIX}/health"):
        response = client.get(path)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["features"] == {"dynamic_courses": mode}
        # The v1 keys are still there and still first-class.
        assert body["status"] == "ok"
        assert body["version"] == "0.1.0"
        assert "database" in body


def test_every_v2_path_in_the_openapi_schema_is_covered_by_this_file() -> None:
    """The drift alarm for the two lists above.

    Enumerating paths by hand is what makes the assertions readable; the cost is that a
    v2 route added later could go unguarded and unnoticed. So the app's own schema is
    the cross-check: every path that carries a v2 router's tag has to appear in one of
    the two tuples.
    """
    schema = create_app().openapi()
    v2_tags = {"Course Schema", "Onboarding", "Learner profile", "Nodes", "Explain"}
    documented = {
        path
        for path, operations in schema["paths"].items()
        if any(
            v2_tags & set(operation.get("tags") or ())
            for operation in operations.values()
            if isinstance(operation, dict)
        )
    }

    def template(path: str) -> str:
        """Turn a concrete path into its OpenAPI template."""
        out = path.split("?")[0]
        for value in (COURSE_ID, NODE_ID, RENDER_ID, PROBE_ID):
            out = out.replace(str(value), "{X}")
        return out

    covered = {
        template(f"{PREFIX}{path}") for _method, path, _body in ADMIN_SURFACE + EMPLOYEE_SURFACE
    }
    expected = {
        template_of_openapi
        for template_of_openapi in (
            path.replace("{course_id}", "{X}")
            .replace("{node_id}", "{X}")
            .replace("{render_id}", "{X}")
            for path in documented
        )
    }
    missing = expected - covered
    assert not missing, f"v2 paths with no flag assertion in this file: {sorted(missing)}"
