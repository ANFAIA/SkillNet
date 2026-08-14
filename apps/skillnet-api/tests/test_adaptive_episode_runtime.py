"""Flagged adaptive runtime branch: ready, decline, routing and prompt selection."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agents.runtime import nodes
from src.agents.runtime.graph import build_node_graph
from src.config import settings
from src.knowledge_pack.contracts import (
    EvidenceSpec,
    MustPreserveAtom,
    MustPreserveKind,
    NodeKnowledgePack,
    PackProvenance,
    PackStatus,
    SourceRef,
)
from src.knowledge_pack.runtime_selection import select_runtime_knowledge
from src.personalization.plan import CognitiveMission, LearningObjective, SourceFunction

HASH_A = "a" * 64
HASH_B = "b" * 64


def _pack(
    *,
    mission: CognitiveMission,
    atom_kind: MustPreserveKind,
    requirements: frozenset[str] = frozenset(),
) -> NodeKnowledgePack:
    node_id = f"node-{mission.value}"
    return NodeKnowledgePack(
        status=PackStatus.READY,
        node_id=node_id,
        title="Grounded objective",
        objective=LearningObjective(
            objective_id=node_id,
            objective_version=1,
            mission=mission,
            source_functions=frozenset({SourceFunction.LOCATE}),
            required_fact_refs=("fact.one",),
            available_requirements=requirements,
        ),
        source_refs=(
            SourceRef(
                ref_id="manual.ref",
                document_id="manual-v1",
                locator="section:one",
                excerpt_hash=HASH_A,
                source_revision="rev-1",
            ),
        ),
        evidence_specs=(
            EvidenceSpec(
                evidence_id="evidence.one",
                description="Grounded evidence",
                atom_refs=("fact.one",),
            ),
        ),
        must_preserve=(
            MustPreserveAtom(
                atom_id="fact.one",
                kind=atom_kind,
                text="The grounded fact.",
                sources=("manual.ref",),
                evidence=("evidence.one",),
                critical=atom_kind is MustPreserveKind.SAFETY_RULE,
            ),
        ),
        provenance=PackProvenance(
            node_id=node_id,
            schema_version=1,
            source_bundle_hash=HASH_A,
            semantic_hash=HASH_B,
            generator="fixture/1",
        ),
    )


def _state(pack: NodeKnowledgePack, *, criticality: str = "recommended") -> dict:
    selection = select_runtime_knowledge(
        pack.canonical_payload(),
        profile=SimpleNamespace(
            experience_level="some",
            preset="standard",
            format_vector={},
            learning_preferences={},
            nodes_completed=1,
        ),
        node_state=SimpleNamespace(scaffold_band="neutral", last_error_kind=None),
        accessibility={},
        base_density=3,
    )
    assert selection is not None
    return {
        "request_id": "episode-request",
        "org_id": str(uuid.UUID(int=1)),
        "course_id": str(uuid.UUID(int=2)),
        "node_id": str(uuid.UUID(int=3)),
        "node": {
            "id": str(uuid.UUID(int=3)),
            "title": pack.title,
            "outcome": pack.title,
            "domain": "grounded recognition",
            "criticality": criticality,
            "mastery_threshold": 0.8,
        },
        "profile": {
            "experience_level": "some",
            "preset": "standard",
            "format_vector": {},
            "learning_preferences": {},
            "nodes_completed": 1,
        },
        "node_state": {"mastery": 0.2, "scaffold_band": "neutral"},
        "accessibility": {},
        "effective_density": 3,
        "scaffold_band": "neutral",
        "selection_strategy": "top5/v1",
        "knowledge_pack_key": selection.cache_fragment,
        "knowledge_pack_hash": selection.pack_hash,
        "knowledge_selection_hash": selection.selection_hash,
        "knowledge_atom_ids": list(selection.atom_ids),
        "knowledge_evidence_ids": list(selection.evidence_ids),
        "knowledge_pack_payload": selection.pack_payload,
        "knowledge_source_refs": [
            item.model_dump(mode="json") for item in selection.source_refs
        ],
        "source_context": selection.source_context,
    }


async def test_recognition_pack_builds_ready_episode_with_certified_activity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(nodes, "publish_step", AsyncMock())
    monkeypatch.setattr(nodes.sse, "publish", AsyncMock())
    pack = _pack(
        mission=CognitiveMission.RECOGNIZE,
        atom_kind=MustPreserveKind.FACT,
    )

    result = await nodes.direct_episode(_state(pack))

    assert result["episode_status"] == "ready", result
    assert result["ui_format"] == "exercise"
    assert result["assessment_block"] == "DidactActivity"
    assert result["assessment_item_type"] == "didact.quiz.true-false"
    assert result["episode_certified_component_ids"] == ["didact.quiz.true-false"]
    assert "DidactActivity" in result["prompt_component_ids"]


@pytest.mark.parametrize(
    ("pack", "criticality", "reason"),
    [
        (
            _pack(
                mission=CognitiveMission.DECIDE,
                atom_kind=MustPreserveKind.SAFETY_RULE,
            ),
            "critical",
            "critical_oracle_unavailable",
        ),
        (
            _pack(
                mission=CognitiveMission.PRODUCE,
                atom_kind=MustPreserveKind.CRITERION,
                requirements=frozenset({"execution"}),
            ),
            "recommended",
            "execution_oracle_unavailable",
        ),
    ],
)
async def test_unsupported_operational_evidence_declines_to_legacy(
    pack: NodeKnowledgePack,
    criticality: str,
    reason: str,
) -> None:
    result = await nodes.direct_episode(_state(pack, criticality=criticality))

    assert result["episode_brief"] is None
    assert result["episode_decline_reason"] == f"evidence_policy:{reason}"


def test_flag_off_graph_is_legacy_and_flag_on_adds_ready_decline_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ADAPTIVE_EPISODES", False)
    legacy = build_node_graph().get_graph()
    assert "direct_episode" not in legacy.nodes
    assert any(
        edge.source == "probe_gate" and edge.target == "decide_formato"
        for edge in legacy.edges
    )

    monkeypatch.setattr(settings, "ADAPTIVE_EPISODES", True)
    adaptive = build_node_graph().get_graph()
    edges = {(edge.source, edge.data or "", edge.target) for edge in adaptive.edges}
    assert ("probe_gate", "generate", "direct_episode") in edges
    assert ("direct_episode", "ready", "author_activity") in edges
    assert ("direct_episode", "declined", "decide_formato") in edges
    assert ("author_activity", "legacy", "decide_formato") in edges


async def test_genera_ui_invokes_episode_prompt_builders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    async def fake_make_llm(_org_id: uuid.UUID, _tier: str) -> SimpleNamespace:
        return SimpleNamespace(model="fixture/episode")

    async def fake_stream(
        _llm: object,
        system: str,
        user_prompt: str,
        **_kwargs: object,
    ) -> str:
        captured.update(system=system, user=user_prompt)
        return ""

    monkeypatch.setattr(nodes, "_make_llm", fake_make_llm)
    monkeypatch.setattr(nodes, "_stream_program", fake_stream)
    monkeypatch.setattr(nodes, "log_usage", AsyncMock())
    monkeypatch.setattr(nodes, "publish_step", AsyncMock())
    pack = _pack(
        mission=CognitiveMission.RECOGNIZE,
        atom_kind=MustPreserveKind.FACT,
    )
    ready = await nodes.direct_episode(_state(pack))
    ready.update(
        {
            "request_id": "prompt-request",
            "org_id": str(uuid.UUID(int=1)),
            "node": {"criticality": "recommended", "mastery_threshold": 0.8},
            "profile": {},
            "node_state": {},
            "backend": "openui",
            "retry_count": 0,
            "source_context": "Grounded public fact.",
            "prompt_component_ids": ["Table"],
            "assessment_block": "",
        }
    )

    await nodes.genera_ui.__wrapped__(ready)

    assert "experiencia episodica" in captured["system"]
    assert "MISION DEL EPISODIO" in captured["user"]
    assert "ESQUEMA DE ESTA PANTALLA" not in captured["user"]
