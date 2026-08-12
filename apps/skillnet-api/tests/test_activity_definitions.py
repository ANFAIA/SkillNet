import uuid
from types import SimpleNamespace

import pytest
from pydantic import ValidationError as PydanticValidationError

from src.models.activity_definition import ActivityFamily
from src.schemas.activity import ActivityDefinitionCreate, ActivityDefinitionRead
from src.services.activity_definitions import ActivityDefinitionService, operation_payload
from src.services.activity_ports import ActivityPortRegistry, PortDeclined


def authored(**overrides):
    values = {
        "course_id": uuid.uuid4(), "node_id": uuid.uuid4(), "definition_key": "node:q1",
        "component_id": "DidactQuiz", "family": ActivityFamily.ASSESSMENT,
        "public_definition": {"prompt": "2 + 2", "feedback": {"negative": "Revisa la suma."}},
        "private_definition": {"evaluation": {"mode": "exact", "expected": "4"}},
        "required_ports": ["evaluation"], "provenance": {"pack_id": "pack-1"},
    }
    values.update(overrides)
    return ActivityDefinitionCreate(**values)


def activity(**overrides):
    values = dict(id=uuid.uuid4(), component_id="DidactQuiz", family=ActivityFamily.ASSESSMENT,
                  version=1, public_definition={"prompt": "2 + 2"},
                  private_definition={"evaluation": {"mode": "exact", "expected": "4"}},
                  required_ports=["evaluation"], provenance={}, enabled=True)
    values.update(overrides)
    return SimpleNamespace(**values)


def test_public_definition_rejects_answer_keys_recursively():
    with pytest.raises(PydanticValidationError, match="server-owned"):
        authored(public_definition={"items": [{"answer_key": {"correct": 0}}]})


def test_public_projection_never_has_private_definition():
    read = ActivityDefinitionRead.of(activity(), missing_ports=[])
    dumped = read.model_dump(mode="json")
    assert dumped["activity_id"]
    assert dumped["schema_version"] == 1
    assert "private_definition" not in dumped
    assert "answer_key" not in str(dumped)


@pytest.mark.asyncio
async def test_builtin_exact_evaluation_keeps_expected_server_side():
    service = ActivityDefinitionService(SimpleNamespace(), SimpleNamespace())
    result = await service.evaluate(activity(), {"answer": "4"})
    assert result == {"outcome": "correct", "passed": True, "score": 1.0, "feedback": None}
    assert "expected" not in result


@pytest.mark.asyncio
async def test_missing_execution_port_declines_honestly():
    service = ActivityDefinitionService(SimpleNamespace(), SimpleNamespace(), ActivityPortRegistry())
    result = await service.execute(
        activity(family=ActivityFamily.EXECUTION, required_ports=["execution"]), {"code": "print(1)"}
    )
    assert result == PortDeclined("missing_ports:execution")
    assert operation_payload(result)["status"] == "declined"


@pytest.mark.asyncio
async def test_declarative_simulation_declines_an_unknown_transition():
    service = ActivityDefinitionService(SimpleNamespace(), SimpleNamespace())
    row = activity(
        family=ActivityFamily.SIMULATION, required_ports=["simulation"],
        private_definition={"simulation": {"initial": "start", "transitions": {"start": {"go": "done"}}}},
    )
    assert await service.transition(row, {}, "go") == {"current": "done"}
    assert await service.transition(row, {}, "invented") == PortDeclined("transition_not_available")
