from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

from src.knowledge_pack.configured_generator import (
    ConfiguredKnowledgePackGenerator,
    objective_for_node,
)
from src.llm.client import Usage
from src.personalization.plan import CognitiveMission, SourceFunction
from src.services.node_knowledge_pack_service import KnowledgePackSnapshot


class FakeLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0

    async def complete_with_usage(self, *_args, **_kwargs):
        self.calls += 1
        return self.response, Usage(tokens_in=10, tokens_out=5)


def make_node():
    node_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    document_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    return SimpleNamespace(
        id=node_id,
        title="Abrir la caja",
        summary="Comprobar el fondo antes de abrir.",
        source_document_id=document_id,
        source_headings=["Apertura", "Caja"],
        default_ui_format="explanation",
    )


def test_objective_uses_the_existing_shape_detector() -> None:
    objective = objective_for_node(
        make_node(),
        source_context="1. Cuenta el fondo\n2. Registra la diferencia\n3. Informa al encargado",
        schema_version=4,
    )

    assert objective.objective_version == 4
    assert objective.mission is CognitiveMission.RECONSTRUCT
    assert SourceFunction.PROCEDURE in objective.source_functions


async def test_configured_adapter_persists_the_complete_canonical_contract() -> None:
    node = make_node()
    ref_id = f"source:{node.source_document_id}:node:{node.id}"
    sections = {
        "evidence_specs": [],
        "must_preserve": [
            {
                "atom_id": "fact.float-before-open",
                "kind": "fact",
                "text": "El fondo se comprueba antes de abrir.",
                "sources": [ref_id],
                "evidence": [],
                "critical": True,
            }
        ],
        "selectable": [],
        "generable_slots": [],
        "missing_data": [],
    }
    llm = FakeLLM(json.dumps(sections))
    snapshot = KnowledgePackSnapshot(
        org_id=uuid.uuid4(),
        course_id=uuid.uuid4(),
        node_id=node.id,
        source_fingerprint="f" * 64,
        schema_version=2,
        generator_version="knowledge-pack/v1",
    )

    completed = await ConfiguredKnowledgePackGenerator(llm).generate(
        course=SimpleNamespace(id=snapshot.course_id),
        node=node,
        source_context="El fondo se comprueba antes de abrir.",
        snapshot=snapshot,
    )

    assert llm.calls == 2
    assert completed.pack_payload["format"] == "node-knowledge-pack/1"
    assert completed.pack_payload["node_id"] == str(node.id)
    assert len(completed.pack_hash) == 64
    assert set(completed.pack_hash) <= set("0123456789abcdef")
    assert completed.atoms[0]["category"] == "must_preserve"
    assert completed.input_tokens == 20
    assert completed.output_tokens == 10
    assert "fondo se comprueba" in completed.markdown


async def test_draft_source_uses_the_model_when_the_brief_is_usable() -> None:
    node = make_node()
    brief = "\n".join(
        [
            "## Fondo de caja",
            "Antes de abrir se cuenta el fondo y se anota la diferencia.",
            "## Si falta dinero",
            "Se informa al encargado antes de cobrar la primera cuenta.",
        ]
    )
    llm = FakeLLM(brief)
    text = await ConfiguredKnowledgePackGenerator(llm).draft_source(
        course=SimpleNamespace(title="Apertura", description="Turno de manana", outcome=None),
        node=node,
    )

    assert llm.calls == 1
    assert "Fondo de caja" in text


async def test_draft_source_falls_back_to_the_schema_when_the_model_is_thin() -> None:
    node = make_node()
    llm = FakeLLM("ok")
    text = await ConfiguredKnowledgePackGenerator(llm).draft_source(
        course=SimpleNamespace(title="Apertura", description="", outcome=None),
        node=node,
    )

    assert text.startswith("# Abrir la caja")
    assert "Comprobar el fondo" in text
