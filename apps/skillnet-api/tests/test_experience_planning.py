"""Design-time neutral planning: flexible rhythms, baseline variants, idempotency."""

import inspect
import json
import uuid
from dataclasses import asdict
from types import SimpleNamespace

import pytest

import src.services.experience_planning as planning_module
from src.models import CourseNode, NodeCriticality, UiFormat
from src.services.experience_planning import (
    NeutralExperiencePlanner,
    build_node_experience_plan,
)

ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
COURSE_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


def node(
    *,
    criticality: NodeCriticality = NodeCriticality.RECOMMENDED,
    ui_format: UiFormat = UiFormat.EXPLANATION,
    outcome: str = "Aplicar el procedimiento correctamente",
    position: int = 1,
) -> CourseNode:
    row = CourseNode(
        org_id=ORG_ID,
        course_id=COURSE_ID,
        title="Preparar el pedido",
        summary="Procedimiento aprobado para preparar pedidos.",
        outcome=outcome,
        criticality=criticality,
        position=position,
        source_headings=["Preparacion"],
        mastery_threshold=0.9,
        default_ui_format=ui_format,
        archived=False,
    )
    row.id = uuid.uuid4()
    return row


def test_critical_business_training_starts_briefly_but_preserves_safe_practice() -> None:
    plan = build_node_experience_plan(
        node(criticality=NodeCriticality.CRITICAL), schema_version=4
    )

    assert plan.rhythm == "brief_explain_practice_transfer"
    assert [item.intent for item in plan.intents] == [
        "explain",
        "guided_practice",
        "transfer",
    ]
    explanation = plan.intents[0]
    assert explanation.constraints["brief"] is True
    assert explanation.constraints["max_words"] == 90
    assert explanation.constraints["required_before_attempt"] is True
    assert plan.intents[-1].required_evidence == ("safe_transfer",)


def test_noncritical_explanation_is_skippable_and_rhythm_can_change() -> None:
    recommended = build_node_experience_plan(node(), schema_version=2)
    contextual = build_node_experience_plan(
        node(criticality=NodeCriticality.CONTEXTUAL), schema_version=2
    )

    assert recommended.rhythm == "brief_explain_then_apply"
    assert contextual.rhythm == "summary_then_check"
    assert recommended.intents[0].constraints["skippable_when"] == (
        "prior_mastery_or_experience"
    )
    assert contextual.intents[0].constraints["required_before_attempt"] is False


def test_format_and_outcome_shape_capabilities_without_choosing_a_provider() -> None:
    plan = build_node_experience_plan(
        node(ui_format=UiFormat.EXERCISE, outcome="Identificar la opcion correcta"),
        schema_version=1,
    )

    assert plan.intents[1].intent == "knowledge_check"
    assert plan.intents[1].representations == ("interactive", "procedural")
    assert len(plan.variants) == len(plan.intents)
    assert all(item.selection_policy["kind"] == "baseline" for item in plan.variants)

    serialized = json.dumps(
        {
            "intents": [asdict(item) for item in plan.intents],
            "variants": [asdict(item) for item in plan.variants],
        },
        default=str,
    ).lower()
    assert "provider" not in serialized
    assert "implementation_id" not in serialized
    assert "didact" not in serialized


def test_design_time_planner_has_no_llm_dependency() -> None:
    source = inspect.getsource(planning_module)
    assert "from src.llm" not in source
    assert "import src.llm" not in source


class TrackingSession:
    def __init__(self) -> None:
        self.ids: set[uuid.UUID] = set()
        self.executions = 0

    async def execute(self, statement):
        self.executions += 1
        identifier = statement.compile().params["id"]
        inserted = identifier not in self.ids
        self.ids.add(identifier)
        return SimpleNamespace(rowcount=1 if inserted else 0)


@pytest.mark.asyncio
async def test_revalidation_of_the_same_schema_version_does_not_duplicate_rows() -> None:
    session = TrackingSession()
    planner = NeutralExperiencePlanner(session)  # type: ignore[arg-type]
    nodes = [node(criticality=NodeCriticality.CRITICAL)]

    first = await planner.plan_course(
        org_id=ORG_ID,
        course_id=COURSE_ID,
        schema_version=7,
        nodes=nodes,
    )
    second = await planner.plan_course(
        org_id=ORG_ID,
        course_id=COURSE_ID,
        schema_version=7,
        nodes=nodes,
    )

    assert first.inserted_intents == first.planned_intents == 3
    assert first.inserted_variants == first.planned_variants == 3
    assert second.inserted_intents == 0
    assert second.inserted_variants == 0
    assert second.plan_digest == first.plan_digest
