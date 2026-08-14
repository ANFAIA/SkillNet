from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from src.knowledge_pack.contracts import (
    EvidenceSpec,
    MustPreserveAtom,
    MustPreserveKind,
    NodeKnowledgePack,
    PackProvenance,
    PackStatus,
    SelectableAtom,
    SelectableKind,
    SourceRef,
)
from src.knowledge_pack.runtime_selection import select_runtime_knowledge
from src.personalization.plan import (
    CognitiveMission,
    LearningObjective,
    SourceFunction,
)
from src.services.episode_inputs import (
    EpisodeInputDeclineReason,
    EpisodeInputDeclined,
    EpisodeInputs,
    episode_inputs_from_selection,
)

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def _pack(*, domain: str) -> NodeKnowledgePack:
    is_sql = domain == "sql"
    node_id = "sql-null-join" if is_sql else "recover-ticket"
    source_id = "schema.join" if is_sql else "manual.crocantickets"
    mission = CognitiveMission.PRODUCE if is_sql else CognitiveMission.DECIDE
    source_functions = (
        frozenset({SourceFunction.ASSESS, SourceFunction.EXPLORE})
        if is_sql
        else frozenset({SourceFunction.PROCEDURE})
    )
    preserve_kind = MustPreserveKind.CRITERION if is_sql else MustPreserveKind.PROCEDURE_STEP
    selectable_kind = SelectableKind.WORKED_EXAMPLE if is_sql else SelectableKind.CASE
    atom_id = "criterion.null" if is_sql else "step.use-code"
    return NodeKnowledgePack(
        status=PackStatus.READY,
        node_id=node_id,
        title="JOIN con NULL" if is_sql else "Recuperar una entrada",
        objective=LearningObjective(
            objective_id=node_id,
            objective_version=1,
            mission=mission,
            source_functions=source_functions,
            required_fact_refs=(atom_id,),
        ),
        source_refs=(
            SourceRef(
                ref_id=source_id,
                document_id="sql-lab-v1" if is_sql else "crocantickets-manual-v3",
                locator="schema:customers-orders" if is_sql else "section:recover-email",
                excerpt_hash=HASH_A,
                source_revision="rev-1",
            ),
            SourceRef(
                ref_id="unused.appendix",
                document_id="unused-document",
                locator="appendix",
                excerpt_hash=HASH_C,
                source_revision="rev-1",
            ),
        ),
        evidence_specs=(
            EvidenceSpec(
                evidence_id="query-result" if is_sql else "ticket-recovered",
                description="Execution result" if is_sql else "Recovered ticket state",
                atom_refs=(atom_id,),
            ),
        ),
        must_preserve=(
            MustPreserveAtom(
                atom_id=atom_id,
                kind=preserve_kind,
                text=(
                    "Rows without a match preserve NULL on a LEFT JOIN."
                    if is_sql
                    else "Use Código, not Referencia, for this recovery path."
                ),
                sources=(source_id,),
                evidence=("query-result" if is_sql else "ticket-recovered",),
                critical=not is_sql,
            ),
        ),
        selectable=(
            SelectableAtom(
                atom_id="example.join" if is_sql else "case.wrong-email",
                kind=selectable_kind,
                text=(
                    "Inspect a synthetic LEFT JOIN result."
                    if is_sql
                    else "A buyer entered the wrong email address."
                ),
                sources=(source_id,),
                missions=(mission,),
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


def _selection(pack: NodeKnowledgePack):
    result = select_runtime_knowledge(
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
    assert result is not None
    return result


def _node(pack: NodeKnowledgePack, *, domain: str) -> dict[str, object]:
    evidence_id = pack.evidence_specs[0].evidence_id
    return {
        "domain": domain,
        "outcome": pack.title,
        "criticality": "critical" if domain == "ticket operations" else "recommended",
        "evidence_contracts": {
            evidence_id: {
                "evidence_type": "query_execution" if domain == "sql" else "case_state",
                "oracle_ref": "oracle:sql-null-join/1" if domain == "sql" else "oracle:ticket/1",
            }
        },
    }


def test_ticket_procedure_preserves_provenance_and_procedure_affordance() -> None:
    pack = _pack(domain="tickets")
    selection = _selection(pack)

    result = episode_inputs_from_selection(
        pack,
        selection,
        node=_node(pack, domain="ticket operations"),
        profile_bucket={"experience_level": "novice"},
        node_state={"mastery": 0.2, "last_error_kind": "wrong_identifier"},
    )

    assert isinstance(result, EpisodeInputs)
    assert tuple(result.source_map.source_refs) == ("manual.crocantickets",)
    source = result.source_map.source_refs["manual.crocantickets"]
    assert source.document_id == "crocantickets-manual-v3"
    assert source.content_digest == HASH_A
    assert "follow_procedure" in {
        action for item in result.source_map.affordances for action in item.supports_actions
    }
    assert result.competency.evidence_gates[0].oracle_ref == "oracle:ticket/1"
    assert result.belief.recent_error_kinds == ("wrong_identifier",)


def test_sql_projection_exposes_production_and_evaluation_not_ticket_procedure() -> None:
    pack = _pack(domain="sql")
    result = episode_inputs_from_selection(
        pack,
        _selection(pack),
        node=_node(pack, domain="sql"),
        profile_bucket={"experience_level": "experienced"},
        node_state={"mastery": 0.75, "confidence": 0.8},
    )

    assert isinstance(result, EpisodeInputs)
    actions = {
        action for item in result.source_map.affordances for action in item.supports_actions
    }
    assert {"produce", "evaluate"}.issubset(actions)
    assert "follow_procedure" not in actions
    assert result.competency.evidence_gates[0].evidence_type == "query_execution"


def test_missing_required_oracle_declines_instead_of_inventing_one() -> None:
    pack = _pack(domain="sql")

    result = episode_inputs_from_selection(
        pack,
        _selection(pack),
        node={"domain": "sql", "criticality": "recommended"},
    )

    assert result == EpisodeInputDeclined(
        EpisodeInputDeclineReason.MISSING_REQUIRED_EVIDENCE,
        ("query-result",),
    )


def test_atom_prerequisites_do_not_leak_into_competency_prerequisites() -> None:
    pack = _pack(domain="sql")
    selectable = pack.selectable[0].model_copy(
        update={"prereqs": (pack.must_preserve[0].atom_id,)}
    )
    pack = pack.model_copy(update={"selectable": (selectable,)})

    result = episode_inputs_from_selection(
        pack, _selection(pack), node=_node(pack, domain="sql")
    )

    assert isinstance(result, EpisodeInputs)
    assert result.competency.prerequisite_refs == ()


def test_unknown_selection_source_ref_declines() -> None:
    pack = _pack(domain="sql")
    selection = _selection(pack)
    forged = replace(
        selection,
        source_refs=(
            SourceRef(
                ref_id="unknown.source",
                document_id="unknown-document",
                locator="unknown",
                excerpt_hash=HASH_C,
                source_revision="rev-1",
            ),
        ),
    )

    result = episode_inputs_from_selection(
        pack, forged, node=_node(pack, domain="sql")
    )

    assert isinstance(result, EpisodeInputDeclined)
    assert result.reason is EpisodeInputDeclineReason.UNKNOWN_SELECTION_REF
    assert "unknown.source" in result.refs
