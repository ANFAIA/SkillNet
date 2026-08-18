"""Tests for the A2A orchestrator tool dispatch."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_skillnet_client():
    """Mock SkillNetClient responses."""
    with patch("src.tools.SkillNetClient") as mock_cls:
        client = mock_cls.return_value
        client.who_knows = AsyncMock(return_value={
            "items": [
                {"user_id": "abc-123", "full_name": "Maria Lopez", "level": "high"},
                {"user_id": "def-456", "full_name": "Juan Garcia", "level": "medium"},
            ],
            "total": 2,
        })
        client.get_gap = AsyncMock(return_value={
            "gaps": [
                {"skill": "Python", "total_users": 10, "coverage": {"high": 1, "medium": 2, "low": 3, "none": 4}},
                {"skill": "SQL", "total_users": 10, "coverage": {"high": 0, "medium": 1, "low": 2, "none": 7}},
            ]
        })
        client.verify_skill = AsyncMock(return_value={
            "user_id": "abc-123",
            "skill": "Python",
            "level": "high",
            "source": "manual",
        })
        client.list_skills = AsyncMock(return_value={
            "categories": [
                {"name": "Tech", "skills": [{"name": "Python"}, {"name": "SQL"}]},
            ]
        })
        client.get_user_skills = AsyncMock(return_value={
            "user_id": "abc-123",
            "skills": [
                {"name": "Python", "level": "high"},
                {"name": "SQL", "level": "medium"},
            ]
        })
        client.create_course = AsyncMock(return_value={
            "course_id": "course-789",
            "validated": True,
            "packs_ready": 3,
            "node_count": 3,
        })
        yield client


@pytest.mark.asyncio
async def test_execute_tool_who_knows(mock_skillnet_client):
    """Tool executor should call who_knows with correct args."""
    from src.tools import execute_tool

    result = await execute_tool("who_knows", {"skill": "Python", "min_level": "medium"})
    parsed = json.loads(result)

    mock_skillnet_client.who_knows.assert_awaited_once_with(
        skill="Python", min_level="medium"
    )
    assert parsed["total"] == 2
    assert len(parsed["items"]) == 2


@pytest.mark.asyncio
async def test_execute_tool_get_gap(mock_skillnet_client):
    """Tool executor should call get_gap."""
    from src.tools import execute_tool

    result = await execute_tool("get_gap", {})
    parsed = json.loads(result)

    mock_skillnet_client.get_gap.assert_awaited_once()
    assert len(parsed["gaps"]) == 2


@pytest.mark.asyncio
async def test_execute_tool_verify_skill(mock_skillnet_client):
    """Tool executor should call verify_skill with correct args."""
    from src.tools import execute_tool

    result = await execute_tool("verify_skill", {
        "user_id": "abc-123",
        "skill_name": "Python",
        "level": "high",
        "source": "manual",
    })
    parsed = json.loads(result)

    mock_skillnet_client.verify_skill.assert_awaited_once_with(
        user_id="abc-123",
        skill_name="Python",
        level="high",
        source="manual",
    )
    assert parsed["level"] == "high"


@pytest.mark.asyncio
async def test_execute_tool_list_skills(mock_skillnet_client):
    """Tool executor should call list_skills."""
    from src.tools import execute_tool

    result = await execute_tool("list_skills", {})
    parsed = json.loads(result)

    mock_skillnet_client.list_skills.assert_awaited_once()
    assert "categories" in parsed


@pytest.mark.asyncio
async def test_execute_tool_get_user_skills(mock_skillnet_client):
    """Tool executor should call get_user_skills."""
    from src.tools import execute_tool

    result = await execute_tool("get_user_skills", {"user_id": "abc-123"})
    parsed = json.loads(result)

    mock_skillnet_client.get_user_skills.assert_awaited_once_with(user_id="abc-123")
    assert len(parsed["skills"]) == 2


@pytest.mark.asyncio
async def test_execute_tool_create_course(mock_skillnet_client):
    """Tool executor should call create_course with title and optional args."""
    from src.tools import execute_tool

    result = await execute_tool("create_course", {
        "title": "Food safety basics",
        "intent_density": 3,
        "enroll_user_id": "abc-123",
        "generate_artifacts": ["podcast"],
    })
    parsed = json.loads(result)

    mock_skillnet_client.create_course.assert_awaited_once_with(
        title="Food safety basics",
        document_id=None,
        intent_density=3,
        enroll_user_id="abc-123",
        generate_artifacts=["podcast"],
    )
    assert parsed["validated"] is True
    assert parsed["course_id"] == "course-789"


@pytest.mark.asyncio
async def test_execute_tool_unknown():
    """Unknown tool should return error."""
    from src.tools import execute_tool

    result = await execute_tool("nonexistent_tool", {})
    parsed = json.loads(result)

    assert "error" in parsed
    assert "nonexistent_tool" in parsed["error"]


@pytest.mark.asyncio
async def test_agent_card_endpoint():
    """AgentCard endpoint should return valid card."""
    from starlette.testclient import TestClient
    from src.main import app

    client = TestClient(app)
    resp = client.get("/.well-known/agent.json")

    assert resp.status_code == 200
    card = resp.json()
    assert card["name"] == "SkillNet"
    assert len(card["skills"]) == 6
    assert any(s["id"] == "create_course" for s in card["skills"])
    assert card["capabilities"]["streaming"] is False


@pytest.mark.asyncio
async def test_jsonrpc_method_not_found():
    """Unknown JSON-RPC method should return error."""
    from starlette.testclient import TestClient
    from src.main import app

    client = TestClient(app)
    resp = client.post("/", json={
        "jsonrpc": "2.0",
        "method": "unknown/method",
        "params": {},
        "id": 1,
    })

    assert resp.status_code == 200
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == -32601
