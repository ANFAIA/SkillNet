"""``GET /setup/status`` is public and pre-authentication: no hint may travel on it.

A hint names the environment variable a deployment is missing. Telling an anonymous caller
which key is absent is configuration disclosure (docs/design/security.md), so this is a
guard test and not a formality: the whole point of ``include_hints`` is that this endpoint
never passes it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.config import settings
from src.deps.db import get_async_session
from src.main import create_app
from src.schemas.capabilities import Capabilities
from src.services import provider_health


class _NoUsers:
    def scalar_one_or_none(self):  # noqa: ANN201 - mimics a SQLAlchemy Result
        return None


class _FakeSession:
    async def execute(self, *_args, **_kwargs):  # noqa: ANN002, ANN003
        return _NoUsers()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    """A deployment with nothing configured — the state that produces the most hints."""
    provider_health.reset()
    monkeypatch.setattr(settings, "LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setattr(settings, "LLM_API_KEY", "")
    monkeypatch.setattr(settings, "TTS_PROVIDER", "disabled")
    monkeypatch.setattr(settings, "TTS_API_KEY", "")
    monkeypatch.setattr(settings, "IMAGE_API_KEY", "")
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")

    app = create_app()
    app.dependency_overrides[get_async_session] = lambda: _FakeSession()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        provider_health.reset()


def test_the_public_payload_carries_status_and_reason_for_every_capability(client) -> None:
    payload = client.get("/api/v1/setup/status").json()

    capabilities = payload["capabilities"]
    assert set(capabilities) == set(Capabilities.model_fields)
    assert capabilities["images"] == {
        "status": "blocked",
        "reason": "missing_api_key",
        "hint": None,
    }


def test_the_public_payload_never_carries_a_hint(client) -> None:
    payload = client.get("/api/v1/setup/status").json()

    for name, capability in payload["capabilities"].items():
        assert capability["hint"] is None, name


def test_no_environment_variable_name_leaks_into_the_public_payload(client) -> None:
    """Belt and braces: not through ``hint``, and not through anything else either."""
    raw = client.get("/api/v1/setup/status").text

    for secretish in ("API_KEY", "OPENROUTER", "CLIENT_SECRET", ".env"):
        assert secretish not in raw


def test_the_public_payload_carries_the_media_requirements_table(client) -> None:
    """So the frontend disables a Studio button from the backend's table, not a copy."""
    requirements = client.get("/api/v1/setup/status").json()["media_requirements"]

    assert requirements["infographic"] == ["ai", "images"]
    assert requirements["podcast"] == ["ai", "tts"]
    assert requirements["mindmap"] == []
