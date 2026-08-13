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


@pytest.mark.parametrize(
    "private_key",
    [
        "answerKey",
        "accepted_answers",
        "correctMatches",
        "correct_option_ids",
        "evaluation",
        "expectedAnswer",
        "grading",
        "rule",
        "solution",
    ],
)
def test_public_definition_rejects_recursive_solution_aliases(private_key):
    with pytest.raises(PydanticValidationError, match="server-owned"):
        authored(public_definition={"nested": [{"deeper": {private_key: "secret"}}]})


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


@pytest.mark.parametrize(
    ("config", "received", "outcome", "score"),
    [
        ({"mode": "exact", "expected": True}, True, "correct", 1.0),
        ({"mode": "set", "expected": ["a", "b"]}, ["b", "a"], "correct", 1.0),
        (
            {"mode": "normalized_any", "expected": ["Alta prioridad"]},
            "  alta   PRIORIDAD ",
            "correct",
            1.0,
        ),
        (
            {"mode": "assignments", "expected": {"a": "1", "b": "2"}},
            {"a": "1", "b": "x"},
            "partial",
            0.5,
        ),
        (
            {"mode": "sequence", "expected": ["first", "second"]},
            ["first", "wrong"],
            "partial",
            0.5,
        ),
        (
            {"mode": "keyed_text", "expected": {"a": ["one"], "b": ["two", "second"]}},
            {"a": "one", "b": "wrong"},
            "partial",
            0.5,
        ),
        (
            {"mode": "numeric", "value": 10, "absolute_tolerance": 0.2},
            "10.1",
            "correct",
            1.0,
        ),
        (
            {"mode": "numeric", "min": 2, "max": 4},
            "5",
            "incorrect",
            0.0,
        ),
        (
            {"mode": "regions", "expected": ["region-1", "region-2"]},
            {"regionIds": ["region-1", "wrong"], "points": []},
            "partial",
            0.5,
        ),
    ],
)
@pytest.mark.asyncio
async def test_builtin_family_evaluation_is_server_side(config, received, outcome, score):
    service = ActivityDefinitionService(SimpleNamespace(), SimpleNamespace())
    result = await service.evaluate(
        activity(private_definition={"evaluation": config}),
        {"answer": received},
    )

    assert result["outcome"] == outcome
    assert result["score"] == score
    assert not any(
        secret in result
        for secret in ("expected", "correct_answer", "answer_key", "solution")
    )


@pytest.mark.asyncio
async def test_unknown_evaluation_mode_declines_instead_of_guessing():
    service = ActivityDefinitionService(SimpleNamespace(), SimpleNamespace())
    result = await service.evaluate(
        activity(private_definition={"evaluation": {"mode": "semantic_magic"}}),
        {"answer": "anything"},
    )
    assert result == PortDeclined("unsupported_evaluation_mode")


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
