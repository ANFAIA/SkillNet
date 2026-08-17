from __future__ import annotations

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
from src.personalization.plan import (
    CognitiveMission,
    LearningObjective,
    SourceFunction,
)
from src.services.activity_authoring_validators import EVALUATED_COMPONENT_MODES
from src.services.activity_definitions import BUILTIN_EVALUATION_MODES
from src.services.evidence_contract_policy import (
    EVIDENCE_CONTRACT_POLICY_VERSION,
    EvidencePolicyAccepted,
    EvidencePolicyDeclineReason,
    EvidencePolicyDeclined,
    evidence_contracts_for_pack,
)

HASH_A = "a" * 64
HASH_B = "b" * 64


def _pack(
    *,
    node_id: str,
    mission: CognitiveMission,
    source_functions: frozenset[SourceFunction],
    atom_kind: MustPreserveKind,
    selectable_kind: SelectableKind | None = None,
    requirements: frozenset[str] = frozenset(),
) -> NodeKnowledgePack:
    atom_id = f"fact:{node_id}"
    evidence_id = f"evidence:{node_id}"
    return NodeKnowledgePack(
        status=PackStatus.READY,
        node_id=node_id,
        title=node_id,
        objective=LearningObjective(
            objective_id=node_id,
            objective_version=1,
            mission=mission,
            source_functions=source_functions,
            available_requirements=requirements,
            required_fact_refs=(atom_id,),
        ),
        source_refs=(
            SourceRef(
                ref_id=f"source:{node_id}",
                document_id=f"document:{node_id}",
                locator="section:1",
                excerpt_hash=HASH_A,
                source_revision="rev-1",
            ),
        ),
        evidence_specs=(
            EvidenceSpec(
                evidence_id=evidence_id,
                description="Observable evidence",
                atom_refs=(atom_id,),
            ),
        ),
        must_preserve=(
            MustPreserveAtom(
                atom_id=atom_id,
                kind=atom_kind,
                text="Source-backed truth",
                sources=(f"source:{node_id}",),
                evidence=(evidence_id,),
                critical=atom_kind is MustPreserveKind.SAFETY_RULE,
            ),
        ),
        selectable=(
            (
                SelectableAtom(
                    atom_id=f"case:{node_id}",
                    kind=selectable_kind,
                    text="Grounded case",
                    sources=(f"source:{node_id}",),
                    missions=(mission,),
                )
            ,)
            if selectable_kind is not None
            else ()
        ),
        provenance=PackProvenance(
            node_id=node_id,
            schema_version=1,
            source_bundle_hash=HASH_A,
            semantic_hash=HASH_B,
            generator="fixture/1",
        ),
    )


def test_critical_ticket_without_exact_simulator_declines_not_generic_quiz() -> None:
    pack = _pack(
        node_id="recover-ticket",
        mission=CognitiveMission.DECIDE,
        source_functions=frozenset({SourceFunction.PROCEDURE}),
        atom_kind=MustPreserveKind.SAFETY_RULE,
        selectable_kind=SelectableKind.CASE,
    )

    result = evidence_contracts_for_pack(pack, criticality="critical")

    assert isinstance(result, EvidencePolicyDeclined)
    assert result.reason is EvidencePolicyDeclineReason.CRITICAL_ORACLE_UNAVAILABLE
    assert "quiz" not in result.reason.value


def test_recommended_ticket_case_declines_because_rubric_has_no_real_scorer() -> None:
    pack = _pack(
        node_id="ticket-formative-case",
        mission=CognitiveMission.DECIDE,
        source_functions=frozenset({SourceFunction.PROCEDURE, SourceFunction.ASSESS}),
        atom_kind=MustPreserveKind.PROCEDURE_STEP,
        selectable_kind=SelectableKind.CASE,
    )

    result = evidence_contracts_for_pack(pack, criticality="recommended")

    assert isinstance(result, EvidencePolicyDeclined)
    assert result.reason is EvidencePolicyDeclineReason.RUBRIC_ORACLE_UNAVAILABLE
    assert "didact.rubric" not in EVALUATED_COMPONENT_MODES


def test_sql_without_execution_sandbox_declines() -> None:
    pack = _pack(
        node_id="sql-left-join-null",
        mission=CognitiveMission.PRODUCE,
        source_functions=frozenset({SourceFunction.ASSESS, SourceFunction.EXPLORE}),
        atom_kind=MustPreserveKind.CRITERION,
        requirements=frozenset({"evaluation", "execution"}),
    )

    result = evidence_contracts_for_pack(pack, criticality="recommended")

    assert isinstance(result, EvidencePolicyDeclined)
    assert result.reason is EvidencePolicyDeclineReason.EXECUTION_ORACLE_UNAVAILABLE


def test_simple_fact_recognition_uses_existing_exact_scoring() -> None:
    pack = _pack(
        node_id="recognize-refund-window",
        mission=CognitiveMission.RECOGNIZE,
        source_functions=frozenset({SourceFunction.LOCATE}),
        atom_kind=MustPreserveKind.FACT,
    )

    result = evidence_contracts_for_pack(pack, criticality="recommended")

    assert isinstance(result, EvidencePolicyAccepted)
    assert result.policy_version == EVIDENCE_CONTRACT_POLICY_VERSION
    contract = result.evidence_contracts["evidence:recognize-refund-window"]
    assert contract["evaluation_mode"] == "exact"
    # A FAMILY of deterministically-scored recognition components is certified so the rich
    # interactive Didact activities (matching/categorize/word-bank/sort) can surface, not
    # only true/false. Every id must be backed by a built-in scorer.
    supported = contract["supported_component_ids"]
    assert "didact.quiz.true-false" in supported
    assert "didact.matching" in supported
    assert all(
        EVALUATED_COMPONENT_MODES[cid] in BUILTIN_EVALUATION_MODES for cid in supported
    )
    assert "exact" in BUILTIN_EVALUATION_MODES
    assert contract["oracle_ref"].startswith("activity-definition-evaluation/1:")
