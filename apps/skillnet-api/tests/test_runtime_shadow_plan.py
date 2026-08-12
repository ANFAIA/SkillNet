"""The shadow planner observes OpenUI renders but cannot steer them."""

from __future__ import annotations

import json
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from src.agents.runtime import shadow_plan
from src.agents.runtime import nodes as runtime_nodes


def _state() -> dict:
    return {
        "node_id": "temperature-check",
        "schema_version": 2,
        "node": {"title": "Control de temperatura"},
        "profile": {
            "nodes_completed": 5,
            "experience_level": "experienced",
            "preset": "standard",
            "format_vector": {"dato": 0.8, "texto": 0.2},
        },
        "node_state": {"last_error_kind": "procedural"},
        "ui_format": "mixed",
        "effective_density": 4,
        "scaffold_band": "advanced",
        "shape_functions": ["cuantificar"],
        "shape_summary": "numeric_seriesx4->Table",
        "assessment_block": "QuizItem",
        "assessment_item_type": "numeric",
    }


def test_shadow_trace_is_json_safe_and_keeps_live_decision_separate() -> None:
    state = _state()
    before = deepcopy(state)
    trace = shadow_plan.build_shadow_plan_trace(state)

    assert trace["status"] == "planned"
    assert trace["mode"] == "shadow"
    assert trace["live"] == {
        "ui_format": "mixed",
        "shape_functions": ["cuantificar"],
        "shape_summary": "numeric_seriesx4->Table",
        "assessment_block": "QuizItem",
        "assessment_item_type": "numeric",
    }
    assert trace["shadow"]["mission"] == "interpret"
    assert trace["shadow"]["objective_version"] == 2
    assert trace["shadow"]["component_candidates"][0]["component_id"] == "Table"
    assert trace["projection"]["inferred_presentation_bucket"] == "data-high"
    # The live density supports 1..5; the experimental contract currently has 3 bands.
    assert trace["projection"]["density"] == 3
    json.dumps(trace)
    assert state == before


def test_inferred_affinity_is_not_promoted_to_declared_preference() -> None:
    trace = shadow_plan.build_shadow_plan_trace(_state())

    assert trace["projection"]["declared_presentations"] == []
    assert "DECLARED_PRESENTATION_MATCHED" not in trace["shadow"]["rationale_codes"]


def test_shadow_planner_fails_open(monkeypatch) -> None:
    def broken_planner(*_args, **_kwargs):
        raise RuntimeError("experimental planner unavailable")

    monkeypatch.setattr(shadow_plan, "plan_experience", broken_planner)

    trace = shadow_plan.build_shadow_plan_trace(_state())

    assert trace["status"] == "error"
    assert trace["error_code"] == "RuntimeError"
    assert trace["live"]["ui_format"] == "mixed"


def test_missing_shape_function_uses_deterministic_format_fallback() -> None:
    state = _state()
    state["shape_functions"] = []
    state["ui_format"] = "exercise"

    trace = shadow_plan.build_shadow_plan_trace(state)

    assert trace["status"] == "planned"
    assert trace["shadow"]["mission"] == "decide"
    assert trace["shadow"]["source_functions"] == ["assess"]
    assert trace["mission_rationale"] == "MISSION_FROM_UI_FORMAT_FALLBACK"


def test_first_shape_function_sets_mission_without_alphabetical_reordering() -> None:
    state = _state()
    state["shape_functions"] = ["cuantificar", "procedimentar"]

    trace = shadow_plan.build_shadow_plan_trace(state)

    assert trace["status"] == "planned"
    assert trace["shadow"]["mission"] == "interpret"
    assert trace["mission_rationale"] == "MISSION_FROM_FIRST_SHAPE_FUNCTION"


@pytest.mark.asyncio
async def test_decide_formato_observes_once_before_either_openui_generator(
    monkeypatch,
) -> None:
    observed: list[dict] = []

    async def keep_detected_shape(_state: dict, _node: dict, plan):
        return plan

    def capture(state: dict) -> dict:
        observed.append(state)
        return {"trace_version": "plan-trace/test", "status": "planned"}

    monkeypatch.setattr(shadow_plan, "build_shadow_plan_trace", capture)
    monkeypatch.setattr(runtime_nodes, "_route_function", keep_detected_shape)
    monkeypatch.setattr(runtime_nodes, "publish_step", AsyncMock())
    monkeypatch.setattr(runtime_nodes.sse, "publish", AsyncMock())
    state = {
        "request_id": "request-1",
        "node_id": "node-1",
        "schema_version": 1,
        "node": {
            "id": "node-1",
            "title": "Protocolo",
            "summary": "Completar los pasos en orden",
            "default_ui_format": "explanation",
            "criticality": "recommended",
        },
        "profile": {
            "nodes_completed": 0,
            "experience_level": "some",
            "preset": "standard",
            "format_vector": {},
        },
        "node_state": {},
        "source_context": "1. Preparar\n2. Comprobar\n3. Registrar",
        "effective_density": 2,
        "scaffold_band": "neutral",
        "ui_spec": {"root": "unchanged"},
    }

    result = await runtime_nodes.decide_formato(state)

    assert len(observed) == 1
    assert observed[0]["assessment_block"] in {"QuizItem", "DragOrder"}
    assert observed[0]["shape_functions"] == ["procedimentar"]
    assert result["plan_trace"]["trace_version"] == "plan-trace/test"
    assert "ui_spec" not in result
    assert state["ui_spec"] == {"root": "unchanged"}
