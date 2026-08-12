import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agents.runtime import nodes as runtime_nodes
from src.schemas.activity import assert_public_payload
from src.services.activity_authoring import (
    ActivityAuthoringDraft,
    build_activity_authoring_prompts,
    materialize_authored_activity,
    split_public_private,
    stable_definition_key,
    validate_authoring_draft,
)
from src.services.activity_authoring_validators import AUTHORING_VALIDATORS


class DefinitionRepo:
    def __init__(self):
        self.row = None

    async def get_version(self, **_kwargs):
        return self.row

    async def create(self, **values):
        self.row = SimpleNamespace(id=uuid.uuid4(), enabled=True, **values)
        return self.row

    async def update(self, row, **values):
        for key, value in values.items():
            setattr(row, key, value)
        return row


def test_recursive_split_keeps_answers_out_of_public_tree():
    public, private = split_public_private(
        {
            "prompt": "Ordena el protocolo",
            "steps": [
                {"label": "Avisar", "correct_order": 2},
                {"label": "Asegurar", "correct_order": 1},
            ],
            "feedback": {"negative": "Revisa el orden"},
        }
    )

    assert public == {
        "prompt": "Ordena el protocolo",
        "steps": [{"label": "Avisar"}, {"label": "Asegurar"}],
        "feedback": {"negative": "Revisa el orden"},
    }
    assert private["steps"] == [
        {"index": 0, "value": {"correct_order": 2}},
        {"index": 1, "value": {"correct_order": 1}},
    ]
    assert_public_payload(public)
    assert "correct_order" not in json.dumps(public)


def test_authoring_prompt_never_requests_or_contains_an_activity_uuid():
    system, user = build_activity_authoring_prompts(
        candidates=["didact.matching"],
        title="Clasificar incidencias",
        outcome="Distinguir prioridades",
        source_context="[atom-1] Prioridad alta implica impacto total.",
        allowed_source_refs=["atom-1"],
    )

    assert "No inventes UUID" in system
    payload = json.loads(user)
    assert payload["candidate_component_ids"] == ["didact.matching"]
    assert "activity_id" not in payload


@pytest.mark.asyncio
async def test_fixture_draft_materialises_stable_id_and_private_answer_server_side():
    from src.services.activity_definitions import ActivityDefinitionService

    repo = DefinitionRepo()
    service = ActivityDefinitionService(repo, SimpleNamespace())
    ids = {
        "org_id": uuid.uuid4(),
        "course_id": uuid.uuid4(),
        "node_id": uuid.uuid4(),
        "render_id": uuid.uuid4(),
    }
    fixture = ActivityAuthoringDraft.model_validate(
        {
            "component_id": "didact.quiz.single-choice",
            "definition": {
                "prompt": "¿Qué prioridad corresponde?",
                "options": ["Alta", "Baja"],
                "correct_answer": "Alta",
            },
            "source_refs": ["atom-priority"],
        }
    )

    first = await materialize_authored_activity(
        service,
        **ids,
        knowledge_pack_id=None,
        pack_hash="pack-a",
        draft=fixture,
        allowed_component_ids=["didact.quiz.single-choice"],
        allowed_source_refs=["atom-priority"],
    )
    second = await materialize_authored_activity(
        service,
        **ids,
        knowledge_pack_id=None,
        pack_hash="pack-a",
        draft=fixture,
        allowed_component_ids=["didact.quiz.single-choice"],
        allowed_source_refs=["atom-priority"],
    )

    assert first.activity_id == second.activity_id == repo.row.id
    assert repo.row.public_definition == {
        "prompt": "¿Qué prioridad corresponde?",
        "options": ["Alta", "Baja"],
    }
    assert repo.row.private_definition == {
        "correct_answer": "Alta",
        "evaluation": {"mode": "exact", "expected": "Alta"},
    }
    assert "correct_answer" not in json.dumps(first.model_dump(mode="json"))
    assert repo.row.source_render_id == ids["render_id"]
    assert repo.row.provenance["source_refs"] == ["atom-priority"]


def test_stable_key_changes_with_render_pack_or_component():
    node = uuid.uuid4()
    render = uuid.uuid4()
    base = stable_definition_key(
        node_id=node, render_id=render, pack_hash="a", component_id="didact.matching"
    )
    assert base == stable_definition_key(
        node_id=node, render_id=render, pack_hash="a", component_id="didact.matching"
    )
    assert base != stable_definition_key(
        node_id=node, render_id=render, pack_hash="b", component_id="didact.matching"
    )


def test_boxing_data_explorer_without_dataset_or_refs_is_declined_before_persist():
    """Regression: the boxing render selected an empty chart and invented punch data."""

    draft = ActivityAuthoringDraft.model_validate(
        {
            "component_id": "didact.data-explorer",
            "definition": {
                "definition": {
                    "id": "boxing-punches",
                    "title": "Potencia de golpes de boxeo",
                    "description": "El cruzado genera 40% mas potencia que el jab.",
                    "axes": {},
                    "series": [],
                }
            },
            "source_refs": [],
        }
    )

    with pytest.raises(ValueError, match="must cite at least one"):
        validate_authoring_draft(
            draft,
            allowed_component_ids=["didact.data-explorer"],
            allowed_source_refs=["atom-boxing"],
        )

    with pytest.raises(ValueError, match="requires grounded source refs"):
        validate_authoring_draft(
            draft,
            allowed_component_ids=["didact.data-explorer"],
            allowed_source_refs=[],
        )


def _valid_shell_definitions():
    return {
        "didact.rubric": {
            "title": "Autoevaluacion",
            "criteria": [{
                "id": "guard",
                "label": "Guardia",
                "levels": [{"id": "safe", "label": "Segura"}, {"id": "open", "label": "Abierta"}],
            }],
        },
        "didact.data-explorer": {
            "definition": {
                "schemaVersion": "1.0.0",
                "id": "impact",
                "title": "Impacto observado",
                "axes": {
                    "x": {"label": "Intento", "domain": {"scale": "linear", "min": 0, "max": 2}},
                    "y": {"label": "Valor", "domain": {"scale": "linear", "min": 0, "max": 10}},
                },
                "series": [{
                    "id": "observed",
                    "label": "Observado",
                    "kind": "line",
                    "source": {"kind": "points", "points": [{"id": "p1", "x": 1, "y": 4}]},
                }],
                "table": {"source": "series", "caption": "Datos de la fuente"},
            }
        },
        "didact.self-explanation-prompt": {"prompt": "Explica la decision.", "scaffolds": ["Cita una evidencia."]},
        "didact.concept-map": {
            "definition": {
                "id": "map", "title": "Relaciones", "nodes": [
                    {"id": "a", "label": "Ataque"}, {"id": "b", "label": "Defensa"},
                ],
                "initialRelations": [{"id": "r", "from": "a", "to": "b", "label": "responde"}],
            }
        },
        "didact.drawing-response": {
            "definition": {"id": "draw", "title": "Trayectoria", "instructions": "Marca el recorrido.", "tools": ["line", "marker"]}
        },
        "didact.equation-workbench": {
            "definition": {"id": "eq", "title": "Transformacion", "instructions": "Despeja x.", "initialExpression": "2x=4"}
        },
        "didact.evidence-annotation": {
            "definition": {
                "id": "evidence", "title": "Encuentra evidencia",
                "segments": [{"id": "s1", "text": "Mantener la guardia alta."}],
                "categories": [{"id": "rule", "label": "Regla"}],
            }
        },
        "didact.measurement-lab": {
            "definition": {
                "id": "measure", "title": "Lee la escala", "observedReading": 4,
                "instrument": {"kind": "linear", "min": 0, "max": 10, "step": 1, "unit": "cm"},
            }
        },
    }


@pytest.mark.parametrize("component_id", sorted(AUTHORING_VALIDATORS))
def test_every_enabled_activity_shell_has_an_executable_authoring_contract(component_id):
    draft = ActivityAuthoringDraft(
        component_id=component_id,
        definition=_valid_shell_definitions()[component_id],
        source_refs=["atom-1"],
    )

    public, _private, _ports, _family = validate_authoring_draft(
        draft,
        allowed_component_ids=[component_id],
        allowed_source_refs=["atom-1"],
    )

    assert public == _valid_shell_definitions()[component_id]


def test_data_explorer_declines_missing_series_even_when_it_cites_a_source():
    definition = _valid_shell_definitions()["didact.data-explorer"]
    definition["definition"]["series"] = []
    draft = ActivityAuthoringDraft(
        component_id="didact.data-explorer", definition=definition, source_refs=["atom-1"]
    )

    with pytest.raises(ValueError, match="series must contain"):
        validate_authoring_draft(
            draft,
            allowed_component_ids=["didact.data-explorer"],
            allowed_source_refs=["atom-1"],
        )


@pytest.mark.asyncio
async def test_runtime_authoring_does_not_call_model_when_activity_not_requested(monkeypatch):
    make_llm = AsyncMock()
    monkeypatch.setattr(runtime_nodes, "_make_llm", make_llm)

    result = await runtime_nodes.author_activity(
        {
            "request_id": "r",
            "plan_trace": {"shadow": {"component_candidates": []}},
            "prompt_component_ids": ["Table", "QuizItem"],
        }
    )

    assert result == {
        "authored_activity": None,
        "activity_authoring_status": "not_requested",
    }
    make_llm.assert_not_awaited()


@pytest.mark.asyncio
async def test_runtime_authoring_declines_to_legacy_without_setting_graph_error(monkeypatch):
    monkeypatch.setattr(runtime_nodes, "_activity_candidates", lambda _state: ("didact.matching",))
    monkeypatch.setattr(runtime_nodes, "publish_step", AsyncMock())
    monkeypatch.setattr(runtime_nodes, "_make_llm", AsyncMock(side_effect=RuntimeError("offline")))

    result = await runtime_nodes.author_activity(
        {
            "request_id": "r",
            "org_id": str(uuid.uuid4()),
            "course_id": str(uuid.uuid4()),
            "node_id": str(uuid.uuid4()),
            "render_id": str(uuid.uuid4()),
            "node": {"title": "Prioridades"},
            "source_context": "Fuente",
            "prompt_component_ids": ["DidactActivity", "Table"],
        }
    )

    assert result["activity_authoring_status"] == "declined:RuntimeError"
    assert result["prompt_component_ids"] == ["Table"]
    assert "error" not in result


@pytest.mark.asyncio
async def test_runtime_authoring_accounts_for_the_optional_model_call(monkeypatch):
    from src.llm.client import Usage

    llm = SimpleNamespace(
        model="fixture-small",
        complete_with_usage=AsyncMock(
            return_value=("{}", Usage(tokens_in=12, tokens_out=4))
        ),
    )
    log_usage = AsyncMock()
    monkeypatch.setattr(runtime_nodes, "_activity_candidates", lambda _state: ("didact.rubric",))
    monkeypatch.setattr(runtime_nodes, "publish_step", AsyncMock())
    monkeypatch.setattr(runtime_nodes, "_make_llm", AsyncMock(return_value=llm))
    monkeypatch.setattr(runtime_nodes, "log_usage", log_usage)

    result = await runtime_nodes.author_activity(
        {
            "request_id": "r",
            "org_id": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4()),
            "course_id": str(uuid.uuid4()),
            "node_id": str(uuid.uuid4()),
            "render_id": str(uuid.uuid4()),
            "node": {"title": "Prioridades"},
            "source_context": "Fuente",
            "knowledge_atom_ids": ["atom-1"],
            "prompt_component_ids": ["DidactActivity", "Table"],
        }
    )

    assert result["activity_authoring_status"] == "declined:ValidationError"
    log_usage.assert_awaited_once()
    assert log_usage.await_args.kwargs["use_case"] == "runtime_activity_authoring"
    assert log_usage.await_args.kwargs["tokens_in"] == 12
    assert log_usage.await_args.kwargs["tokens_out"] == 4
