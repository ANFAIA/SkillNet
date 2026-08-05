"""Stateless schema proposal endpoint: POST /api/v1/ai/schema-propose.

No database, no network, no persistence. The endpoint calls the LLM twice
(theme extraction + schema design) and returns the proposed nodes directly.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.deps.auth import current_user
from src.deps.db import get_async_session
from src.deps.llm import get_llm_service
from src.llm.client import LLMConfig, LLMService
from src.main import create_app
from src.models import UserRole

PREFIX = "/api/v1"
URL = f"{PREFIX}/ai/schema-propose"

ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------
@dataclass
class FakeUser:
    id: uuid.UUID = USER_ID
    org_id: uuid.UUID = ORG_ID
    role: UserRole = UserRole.ADMIN
    accessibility: dict = field(default_factory=dict)


class FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalar_one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalars(self) -> FakeResult:
        return self

    def all(self) -> list[Any]:
        return list(self._rows)


class StubSession:
    async def execute(self, _query: Any) -> FakeResult:
        return FakeResult([])

    async def get(self, _model: Any, _pk: Any) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


THEMES_RESPONSE = json.dumps(
    {"themes": [{"name": "Fundamentos", "description": "Postura y guardia"}]},
    ensure_ascii=False,
)

DESIGN_RESPONSE = json.dumps(
    {
        "nodes": [
            {
                "title": "Fundamentos del boxeo",
                "summary": "Postura, guardia y movimiento basico en el ring",
                "outcome": "El alumno adopta la postura correcta",
                "criticality": "critical",
                "default_ui_format": "explanation",
                "estimated_minutes": 10,
                "source_headings": [],
                "prerequisites": [],
            },
            {
                "title": "Golpes basicos",
                "summary": "Jab, cross, hook y uppercut",
                "outcome": "Ejecutar los cuatro golpes basicos",
                "criticality": "recommended",
                "default_ui_format": "explanation",
                "estimated_minutes": 12,
                "source_headings": [],
                "prerequisites": [0],
            },
        ]
    },
    ensure_ascii=False,
)


class FakeLLMService(LLMService):
    """Returns canned responses keyed by the system prompt."""

    def __init__(self, calls: list[dict[str, str]]) -> None:
        # Skip the parent __init__ validation (no real config).
        self._config = LLMConfig(model="fake/test", api_base=None, api_key=None)
        self._calls = calls
        self.recorded_calls: list[dict[str, Any]] = []

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> str:
        self.recorded_calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "json_mode": json_mode,
            }
        )
        for call in self._calls:
            if call["match"] in system_prompt:
                return call["response"]
        raise AssertionError(f"No canned response for system prompt: {system_prompt[:100]}")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def fake_llm() -> FakeLLMService:
    return FakeLLMService(
        [
            {"match": "temas clave", "response": THEMES_RESPONSE},
            {"match": "disenador instruccional", "response": DESIGN_RESPONSE},
        ]
    )


@pytest.fixture
def client(fake_llm: FakeLLMService) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_async_session] = lambda: StubSession()
    app.dependency_overrides[current_user] = lambda: FakeUser()
    app.dependency_overrides[get_llm_service] = lambda: fake_llm
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def unauth_client(fake_llm: FakeLLMService) -> TestClient:
    """A client with no user override -- requests are unauthenticated."""
    app = create_app()
    app.dependency_overrides[get_async_session] = lambda: StubSession()
    app.dependency_overrides[get_llm_service] = lambda: fake_llm
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_schema_propose_returns_nodes(client: TestClient) -> None:
    response = client.post(
        URL,
        json={
            "title": "Boxeo",
            "description": "Desde fundamentos hasta preparacion fisica",
            "intent_density": 3,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "nodes" in data
    assert len(data["nodes"]) == 2

    first = data["nodes"][0]
    assert first["title"] == "Fundamentos del boxeo"
    assert first["criticality"] == "critical"
    assert first["estimated_minutes"] == 10
    assert first["source_headings"] == []
    assert first["prerequisites"] == []

    second = data["nodes"][1]
    assert second["title"] == "Golpes basicos"
    assert second["prerequisites"] == [0]


def test_schema_propose_requires_authentication(unauth_client: TestClient) -> None:
    response = unauth_client.post(
        URL,
        json={"title": "Boxeo"},
    )
    assert response.status_code == 401


def test_schema_propose_requires_admin_role(fake_llm: FakeLLMService) -> None:
    app = create_app()
    app.dependency_overrides[get_async_session] = lambda: StubSession()
    app.dependency_overrides[current_user] = lambda: FakeUser(role=UserRole.EMPLOYEE)
    app.dependency_overrides[get_llm_service] = lambda: fake_llm
    tc = TestClient(app, raise_server_exceptions=False)

    response = tc.post(URL, json={"title": "Boxeo"})
    assert response.status_code == 403


def test_schema_propose_validates_title_required(client: TestClient) -> None:
    response = client.post(URL, json={"description": "algo"})
    assert response.status_code == 422


def test_schema_propose_validates_density_range(client: TestClient) -> None:
    response = client.post(URL, json={"title": "X", "intent_density": 0})
    assert response.status_code == 422

    response = client.post(URL, json={"title": "X", "intent_density": 6})
    assert response.status_code == 422


def test_intent_density_reaches_the_prompt(
    client: TestClient, fake_llm: FakeLLMService
) -> None:
    client.post(
        URL,
        json={"title": "Boxeo", "intent_density": 5},
    )
    # The schema designer call is the second one.
    assert len(fake_llm.recorded_calls) == 2
    design_call = fake_llm.recorded_calls[1]
    assert "intent_density=5" in design_call["user_prompt"]
    assert "Muy extenso" in design_call["user_prompt"]


def test_schema_propose_filters_empty_nodes(fake_llm: FakeLLMService) -> None:
    """Nodes with blank title or summary are dropped."""
    fake_llm._calls[1]["response"] = json.dumps(
        {
            "nodes": [
                {
                    "title": "Real node",
                    "summary": "Has a summary",
                    "criticality": "critical",
                    "prerequisites": [],
                },
                {
                    "title": "",
                    "summary": "No title",
                    "criticality": "recommended",
                    "prerequisites": [],
                },
                {
                    "title": "No summary",
                    "summary": "   ",
                    "criticality": "recommended",
                    "prerequisites": [],
                },
            ]
        },
        ensure_ascii=False,
    )
    app = create_app()
    app.dependency_overrides[get_async_session] = lambda: StubSession()
    app.dependency_overrides[current_user] = lambda: FakeUser()
    app.dependency_overrides[get_llm_service] = lambda: fake_llm
    tc = TestClient(app, raise_server_exceptions=False)

    response = tc.post(URL, json={"title": "Boxeo"})
    assert response.status_code == 200
    nodes = response.json()["nodes"]
    assert len(nodes) == 1
    assert nodes[0]["title"] == "Real node"


def test_schema_propose_works_without_description(
    client: TestClient, fake_llm: FakeLLMService
) -> None:
    response = client.post(URL, json={"title": "Boxeo"})
    assert response.status_code == 200
    # The extraction call used only the title as context.
    extraction_call = fake_llm.recorded_calls[0]
    assert "Boxeo" in extraction_call["user_prompt"]
