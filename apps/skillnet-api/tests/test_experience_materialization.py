"""Approved probe/text baselines become immutable definitions and bindings."""

import json
import uuid
from types import SimpleNamespace

import pytest

from src.models import CourseNode, NodeCriticality, UiFormat
from src.services.experience_materialization import (
    ExperienceMaterializer,
    QUIZ_IMPLEMENTATION,
    TEXT_IMPLEMENTATION,
    WORKED_EXAMPLE_IMPLEMENTATION,
)
from src.services.experience_planning import build_node_experience_plan
from src.services.experience_resolver import (
    ExperienceCandidate,
    ExperienceRequirements,
    RuntimeExperienceContext,
    resolve_experience,
)

ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
COURSE_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


def valid_probe() -> tuple[list[dict], dict]:
    items = [
        {
            "item_id": "a",
            "item_type": "test",
            "bloom_level": "apply",
            "question": "Que accion respeta el procedimiento?",
            "options": ["Comprobar la ficha", "Omitir el control", "Improvisar", "Esperar"],
        },
        {
            "item_id": "b",
            "item_type": "test",
            "bloom_level": "understand",
            "question": "Por que se comprueba la ficha?",
            "options": ["Por seguridad", "Por estetica", "Por azar", "No se comprueba"],
        },
    ]
    return items, {
        "a": {"correct": 0, "explanation": "La ficha vigente contiene la regla."},
        "b": {"correct": 0, "explanation": "Evita un error seguro."},
    }


def node(*, with_probe: bool = True) -> CourseNode:
    items, key = valid_probe() if with_probe else ([], {})
    row = CourseNode(
        org_id=ORG_ID,
        course_id=COURSE_ID,
        title="Preparar el pedido",
        summary="Comprueba la ficha vigente antes de preparar el pedido.",
        outcome="Aplicar el procedimiento correctamente",
        criticality=NodeCriticality.RECOMMENDED,
        position=1,
        source_headings=["Preparacion"],
        mastery_threshold=0.8,
        default_ui_format=UiFormat.EXERCISE,
        probe_items=items,
        probe_answer_key=key,
        archived=False,
    )
    row.id = uuid.uuid4()
    return row


class TrackingSession:
    def __init__(self) -> None:
        self.ids: set[uuid.UUID] = set()
        self.rows: dict[str, list[dict]] = {}

    async def execute(self, statement):
        params = dict(statement.compile().params)
        self.rows.setdefault(statement.table.name, []).append(params)
        identifier = params["id"]
        inserted = identifier not in self.ids
        self.ids.add(identifier)
        return SimpleNamespace(rowcount=1 if inserted else 0)


@pytest.mark.asyncio
async def test_honest_didact_explanation_and_probe_become_real_baseline_bindings() -> None:
    target = node()
    plan = build_node_experience_plan(target, schema_version=3)
    session = TrackingSession()
    materializer = ExperienceMaterializer(session)  # type: ignore[arg-type]

    result = await materializer.materialize_course(
        org_id=ORG_ID,
        course_id=COURSE_ID,
        schema_version=3,
        nodes=[target],
        plans=[plan],
    )

    assert result.planned_definitions == result.inserted_definitions == 2
    assert result.planned_bindings == result.inserted_bindings == 2
    assert result.declined == ()

    definitions = session.rows["activity_definitions"]
    explanation = next(
        row
        for row in definitions
        if row["component_id"] == WORKED_EXAMPLE_IMPLEMENTATION
    )
    quiz = next(row for row in definitions if row["component_id"] == QUIZ_IMPLEMENTATION)
    assert explanation["public_definition"]["problem"] == target.outcome
    assert explanation["public_definition"]["steps"][0]["explanation"] == target.summary
    assert quiz["required_ports"] == ["evaluation"]
    assert quiz["private_definition"]["evaluation"]["expected"] == "option-0"
    public_json = json.dumps(quiz["public_definition"]).lower()
    assert "correct" not in public_json
    assert "expected" not in public_json
    assert "ficha vigente contiene" not in public_json


@pytest.mark.asyncio
async def test_text_content_is_used_only_when_didact_has_no_honest_representation() -> None:
    target = node(with_probe=False)
    target.outcome = "Identificar la regla aplicable"
    plan = build_node_experience_plan(target, schema_version=1)
    session = TrackingSession()
    await ExperienceMaterializer(session).materialize_course(  # type: ignore[arg-type]
        org_id=ORG_ID,
        course_id=COURSE_ID,
        schema_version=1,
        nodes=[target],
        plans=[plan],
    )

    definition = session.rows["activity_definitions"][0]
    assert definition["component_id"] == TEXT_IMPLEMENTATION
    assert definition["public_definition"] == {
        "content": target.summary,
        "variant": "lead",
    }


@pytest.mark.asyncio
async def test_materialization_is_idempotent_for_the_same_schema_version() -> None:
    target = node()
    plan = build_node_experience_plan(target, schema_version=5)
    session = TrackingSession()
    materializer = ExperienceMaterializer(session)  # type: ignore[arg-type]

    first = await materializer.materialize_course(
        org_id=ORG_ID,
        course_id=COURSE_ID,
        schema_version=5,
        nodes=[target],
        plans=[plan],
    )
    second = await materializer.materialize_course(
        org_id=ORG_ID,
        course_id=COURSE_ID,
        schema_version=5,
        nodes=[target],
        plans=[plan],
    )

    assert first.inserted_definitions == first.inserted_bindings == 2
    assert second.inserted_definitions == second.inserted_bindings == 0
    assert second.materialization_digest == first.materialization_digest


@pytest.mark.asyncio
async def test_incompatible_probe_declines_without_losing_text_baseline() -> None:
    target = node(with_probe=False)
    plan = build_node_experience_plan(target, schema_version=1)
    result = await ExperienceMaterializer(TrackingSession()).materialize_course(  # type: ignore[arg-type]
        org_id=ORG_ID,
        course_id=COURSE_ID,
        schema_version=1,
        nodes=[target],
        plans=[plan],
    )

    assert result.planned_bindings == 1
    assert [item.reason for item in result.declined] == ["probe_not_compatible"]


@pytest.mark.asyncio
async def test_runtime_resolves_the_persisted_didact_binding_without_llm() -> None:
    target = node()
    plan = build_node_experience_plan(target, schema_version=2)
    session = TrackingSession()
    await ExperienceMaterializer(session).materialize_course(  # type: ignore[arg-type]
        org_id=ORG_ID,
        course_id=COURSE_ID,
        schema_version=2,
        nodes=[target],
        plans=[plan],
    )
    binding = next(
        row
        for row in session.rows["implementation_bindings"]
        if row["implementation_id"] == QUIZ_IMPLEMENTATION
    )
    practice = plan.intents[1]
    resolved = resolve_experience(
        ExperienceRequirements(
            intent=practice.intent,
            learner_actions=frozenset(practice.learner_actions),
            representations=frozenset(practice.representations),
            required_evidence=frozenset(practice.required_evidence),
        ),
        [
            ExperienceCandidate(
                binding_id=str(binding["id"]),
                implementation_ref=f"{binding['implementation_id']}@1",
                provider=binding["provider"],
                intents=frozenset({practice.intent}),
                learner_actions=frozenset(practice.learner_actions),
                representations=frozenset(practice.representations),
                evidence=frozenset(practice.required_evidence),
                required_ports=frozenset(binding["required_ports"]),
            )
        ],
        RuntimeExperienceContext(available_ports=frozenset({"evaluation"})),
    )

    assert resolved.selected is not None
    assert resolved.selected.binding_id == str(binding["id"])
