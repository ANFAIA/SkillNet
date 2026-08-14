import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agents.runtime import nodes as runtime_nodes
from src.personalization.didact_catalog import AuthoringStrategy, load_didact_catalog
from src.schemas.activity import assert_public_payload
from src.services.activity_authoring import (
    ActivityAuthoringDraft,
    authoring_draft_with_server_refs,
    build_activity_authoring_prompts,
    materialize_authored_activity,
    split_public_private,
    stable_definition_key,
    validate_authoring_draft,
)
from src.services.activity_authoring_validators import (
    AUTHORING_CONTRACTS,
    AUTHORING_VALIDATORS,
    ActivityDefinitionShapeError,
    authoring_definition_contract,
)


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


def _model_authoring_payload(source_refs):
    return {
        "component_id": "didact.quiz.true-false",
        "definition": {"statement": "Grounded statement", "correct": True},
        "source_refs": source_refs,
    }


def test_server_refs_replace_model_invented_reference_objects_before_validation():
    draft = authoring_draft_with_server_refs(
        _model_authoring_payload(
            [{"ref_id": "invented", "quote": "model-authored provenance"}]
        ),
        allowed_source_refs=("atom.server", "evidence.server"),
    )

    assert draft.source_refs == ["atom.server", "evidence.server"]


def test_server_refs_replace_empty_model_citations_with_exact_allowlist():
    draft = authoring_draft_with_server_refs(
        _model_authoring_payload([]),
        allowed_source_refs=("source.b", "source.a", "source.b"),
    )

    assert draft.source_refs == ["source.b", "source.a"]


def test_empty_server_reference_set_cannot_create_evaluable_draft():
    with pytest.raises(ValueError, match="server-owned source refs"):
        authoring_draft_with_server_refs(
            _model_authoring_payload(["model-invented"]),
            allowed_source_refs=(),
        )


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
        candidates=["didact.self-explanation-prompt"],
        title="Clasificar incidencias",
        outcome="Distinguir prioridades",
        source_context="[atom-1] Prioridad alta implica impacto total.",
        allowed_source_refs=["atom-1"],
    )

    assert "No inventes UUID" in system
    payload = json.loads(user)
    assert payload["candidate_component_ids"] == ["didact.self-explanation-prompt"]
    assert payload["selected_component_id"] == "didact.self-explanation-prompt"
    assert payload["definition_contract"] == {
        "prompt": "Explica la decisión usando una evidencia de la fuente.",
        "scaffolds": ["Nombra la regla aplicada."],
    }
    assert "activity_id" not in payload


def test_data_explorer_prompt_contains_its_exact_mountable_definition_contract():
    _system, user = build_activity_authoring_prompts(
        candidates=["didact.data-explorer", "didact.rubric"],
        title="Evolución del SLA",
        outcome="Interpretar una serie documentada",
        source_context="[atom-1] El SLA pasó de 8 a 4 horas.",
        allowed_source_refs=["atom-1"],
    )

    payload = json.loads(user)
    assert payload["candidate_component_ids"] == ["didact.data-explorer"]
    assert payload["selected_component_id"] == "didact.data-explorer"
    definition = payload["definition_contract"]["definition"]
    assert definition["schemaVersion"] == "1.0.0"
    assert definition["axes"]["x"]["domain"]["scale"] == "linear"
    assert definition["series"][0]["source"]["kind"] == "points"
    assert definition["series"][0]["source"]["points"]
    assert definition["table"]["source"] == "series"


@pytest.mark.parametrize("component_id", sorted(AUTHORING_VALIDATORS))
def test_every_shell_prompt_contract_is_owned_by_and_passes_its_validator(component_id):
    contract = authoring_definition_contract(component_id)
    AUTHORING_VALIDATORS[component_id](contract)

    _system, user = build_activity_authoring_prompts(
        candidates=[component_id],
        title="Actividad",
        outcome="Practicar con la fuente",
        source_context="[atom-1] Regla documentada.",
        allowed_source_refs=["atom-1"],
    )
    assert json.loads(user)["definition_contract"] == contract


@pytest.mark.parametrize(
    "component",
    load_didact_catalog().components,
    ids=lambda component: component.type_id,
)
def test_registry_authoring_strategy_matches_contract_and_validator(component):
    server_activity = component.authoring_strategy is AuthoringStrategy.SERVER_ACTIVITY

    assert (component.type_id in AUTHORING_CONTRACTS) is server_activity
    assert (component.type_id in AUTHORING_VALIDATORS) is server_activity
    if server_activity:
        contract = authoring_definition_contract(component.type_id)
        AUTHORING_VALIDATORS[component.type_id](contract)
    else:
        with pytest.raises(ActivityDefinitionShapeError, match="no authoring contract"):
            authoring_definition_contract(component.type_id)


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
            "component_id": "didact.rubric",
            "definition": {
                "criteria": [
                    {
                        "id": "priority",
                        "label": "Prioridad",
                        "levels": [
                            {"id": "low", "label": "Baja"},
                            {"id": "high", "label": "Alta"},
                        ],
                    }
                ],
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
        allowed_component_ids=["didact.rubric"],
        allowed_source_refs=["atom-priority"],
    )
    second = await materialize_authored_activity(
        service,
        **ids,
        knowledge_pack_id=None,
        pack_hash="pack-a",
        draft=fixture,
        allowed_component_ids=["didact.rubric"],
        allowed_source_refs=["atom-priority"],
    )

    assert first.activity_id == second.activity_id == repo.row.id
    assert repo.row.public_definition == {"criteria": fixture.definition["criteria"]}
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
            "criteria": [
                {
                    "id": "guard",
                    "label": "Guardia",
                    "levels": [
                        {"id": "safe", "label": "Segura"},
                        {"id": "open", "label": "Abierta"},
                    ],
                }
            ],
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
                "series": [
                    {
                        "id": "observed",
                        "label": "Observado",
                        "kind": "line",
                        "source": {"kind": "points", "points": [{"id": "p1", "x": 1, "y": 4}]},
                    }
                ],
                "table": {"source": "series", "caption": "Datos de la fuente"},
            }
        },
        "didact.self-explanation-prompt": {
            "prompt": "Explica la decision.",
            "scaffolds": ["Cita una evidencia."],
        },
        "didact.concept-map": {
            "definition": {
                "id": "map",
                "title": "Relaciones",
                "nodes": [
                    {"id": "a", "label": "Ataque"},
                    {"id": "b", "label": "Defensa"},
                ],
                "initialRelations": [{"id": "r", "from": "a", "to": "b", "label": "responde"}],
            }
        },
        "didact.drawing-response": {
            "definition": {
                "id": "draw",
                "title": "Trayectoria",
                "instructions": "Marca el recorrido.",
                "tools": ["line", "marker"],
            }
        },
        "didact.equation-workbench": {
            "definition": {
                "id": "eq",
                "title": "Transformacion",
                "instructions": "Despeja x.",
                "initialExpression": "2x=4",
            }
        },
        "didact.evidence-annotation": {
            "definition": {
                "id": "evidence",
                "title": "Encuentra evidencia",
                "segments": [{"id": "s1", "text": "Mantener la guardia alta."}],
                "categories": [{"id": "rule", "label": "Regla"}],
            }
        },
        "didact.measurement-lab": {
            "definition": {
                "id": "measure",
                "title": "Lee la escala",
                "observedReading": 4,
                "instrument": {"kind": "linear", "min": 0, "max": 10, "step": 1, "unit": "cm"},
            }
        },
    }


@pytest.mark.parametrize(
    "component_id",
    sorted(
        set(AUTHORING_VALIDATORS)
        - {"didact.hotspot", "didact.label-diagram", "didact.interactive-media"}
    ),
)
def test_every_enabled_activity_shell_has_an_executable_authoring_contract(component_id):
    definition = _valid_shell_definitions().get(
        component_id,
        authoring_definition_contract(component_id),
    )
    draft = ActivityAuthoringDraft(
        component_id=component_id,
        definition=definition,
        source_refs=["atom-1"],
    )

    public, _private, _ports, _family = validate_authoring_draft(
        draft,
        allowed_component_ids=[component_id],
        allowed_source_refs=["atom-1"],
    )

    expected_public, _ = split_public_private(definition)
    assert public == expected_public
    assert "evaluation" not in json.dumps(public)


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


def test_evaluated_family_declines_an_answer_key_that_references_unknown_public_ids():
    definition = authoring_definition_contract("didact.matching")
    definition["evaluation"]["expected"]["source-1"] = "invented-target"
    draft = ActivityAuthoringDraft(
        component_id="didact.matching",
        definition=definition,
        source_refs=["atom-1"],
    )

    with pytest.raises(ActivityDefinitionShapeError, match="unknown ids"):
        validate_authoring_draft(
            draft,
            allowed_component_ids=["didact.matching"],
            allowed_source_refs=["atom-1"],
        )


def test_hotspot_requires_allowed_asset_ref_and_verified_geometry():
    asset_ref = "skasset_opaque"
    definition = authoring_definition_contract("didact.hotspot")
    definition["assetRef"] = asset_ref
    definition["sourceRefs"] = ["atom-1"]
    definition["geometry"]["verified"] = False
    draft = ActivityAuthoringDraft(
        component_id="didact.hotspot",
        definition=definition,
        source_refs=["atom-1", asset_ref],
    )
    with pytest.raises(ValueError, match="independently verified"):
        validate_authoring_draft(
            draft,
            allowed_component_ids=["didact.hotspot"],
            allowed_source_refs=["atom-1", asset_ref],
        )

    definition["geometry"]["verified"] = True
    public, private, ports, _family = validate_authoring_draft(
        draft.model_copy(update={"definition": definition}),
        allowed_component_ids=["didact.hotspot"],
        allowed_source_refs=["atom-1", asset_ref],
    )
    assert public["regions"][0]["id"] == "region-1"
    assert private["evaluation"]["expected"] == ["region-1"]
    assert ports == ["assets", "evaluation"]


def test_interactive_media_rejects_checkpoint_outside_duration():
    asset_ref = "skasset_media"
    definition = authoring_definition_contract("didact.interactive-media")
    definition["assetRef"] = asset_ref
    definition["definition"]["media"]["assetRef"] = asset_ref
    definition["definition"]["checkpoints"][0]["atMs"] = 60_001
    draft = ActivityAuthoringDraft(
        component_id="didact.interactive-media",
        definition=definition,
        source_refs=["c1", asset_ref],
    )
    with pytest.raises(ValueError, match="within duration"):
        validate_authoring_draft(
            draft,
            allowed_component_ids=["didact.interactive-media"],
            allowed_source_refs=["c1", asset_ref],
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
async def test_runtime_uses_prepared_binding_without_calling_authoring_model(monkeypatch):
    binding = SimpleNamespace(
        id=uuid.uuid4(),
        implementation_id="didact.quiz.single-choice",
        implementation_version=1,
        definition_ref=str(uuid.uuid4()),
    )
    intent = SimpleNamespace(id=uuid.uuid4())
    activity = SimpleNamespace(
        id=uuid.UUID(binding.definition_ref),
        component_id="didact.quiz.single-choice",
    )

    class Result:
        def first(self):
            return binding, SimpleNamespace(), intent, activity

    class Session:
        async def execute(self, _query):
            return Result()

    class Context:
        async def __aenter__(self):
            return Session()

        async def __aexit__(self, *_args):
            return None

    make_llm = AsyncMock(side_effect=AssertionError("prepared binding reached LLM"))
    monkeypatch.setattr(
        runtime_nodes,
        "_activity_candidates",
        lambda _state: ("didact.quiz.single-choice",),
    )
    monkeypatch.setattr(runtime_nodes, "async_session_factory", lambda: Context())
    monkeypatch.setattr(runtime_nodes, "_make_llm", make_llm)

    result = await runtime_nodes.author_activity(
        {
            "request_id": "r",
            "org_id": str(uuid.uuid4()),
            "node_id": str(uuid.uuid4()),
            "prompt_component_ids": ["DidactActivity", "Table"],
        }
    )

    assert result["activity_authoring_status"] == "prepared"
    assert result["authored_activity"]["experience_id"] == str(binding.id)
    assert result["authored_activity"]["implementation_ref"] == (
        "didact.quiz.single-choice@1"
    )
    assert result["prompt_component_ids"] == ["LearningExperience", "Table"]
    make_llm.assert_not_awaited()


@pytest.mark.parametrize(
    "component_id",
    [
        component.type_id
        for component in load_didact_catalog().components
        if component.authoring_strategy is AuthoringStrategy.UNSUPPORTED
    ],
)
@pytest.mark.asyncio
async def test_runtime_authoring_declines_unsupported_before_calling_model(
    monkeypatch, component_id
):
    make_llm = AsyncMock(side_effect=AssertionError("unsupported component reached LLM"))
    monkeypatch.setattr(runtime_nodes, "_activity_candidates", lambda _state: (component_id,))
    monkeypatch.setattr(runtime_nodes, "publish_step", AsyncMock())
    monkeypatch.setattr(runtime_nodes, "_make_llm", make_llm)

    result = await runtime_nodes.author_activity(
        {
            "request_id": "r",
            "org_id": str(uuid.uuid4()),
            "course_id": str(uuid.uuid4()),
            "node_id": str(uuid.uuid4()),
            "render_id": str(uuid.uuid4()),
            "node": {"title": "Prioridades"},
            "source_context": "Fuente",
            "knowledge_atom_ids": ["atom.server"],
            "prompt_component_ids": ["DidactActivity", "Table"],
        }
    )

    assert result["activity_authoring_status"] == "declined:ActivityDefinitionShapeError"
    assert result["prompt_component_ids"] == ["Table"]
    assert "error" not in result
    make_llm.assert_not_awaited()


@pytest.mark.asyncio
async def test_runtime_authoring_accounts_for_the_optional_model_call(monkeypatch):
    from src.llm.client import Usage
    from src.models import USE_CASES

    assert "runtime_activity_authoring" in USE_CASES

    llm = SimpleNamespace(
        model="fixture-small",
        complete_with_usage=AsyncMock(return_value=("{}", Usage(tokens_in=12, tokens_out=4))),
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
    assert result["tokens_in"] == 12
    assert result["tokens_out"] == 4
    log_usage.assert_awaited_once()
    assert log_usage.await_args.kwargs["use_case"] == "runtime_activity_authoring"
    assert log_usage.await_args.kwargs["tokens_in"] == 12
    assert log_usage.await_args.kwargs["tokens_out"] == 4
