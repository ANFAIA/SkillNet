"""Pure projection from selected knowledge into provider-neutral episode inputs.

No renderer, component catalogue or LLM participates here.  The adapter is intentionally
fail-closed: a knowledge pack can describe evidence without containing an executable
oracle, so the caller must supply the server-owned evidence contract on the node.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from src.knowledge_pack.contracts import (
    MustPreserveAtom,
    MustPreserveKind,
    NodeKnowledgePack,
    SelectableAtom,
    SelectableKind,
)
from src.knowledge_pack.runtime_selection import RuntimeKnowledgeSelection
from src.personalization.plan import CognitiveMission, Presentation, SourceFunction
from src.schemas.episode_contracts import (
    CompetencyContract,
    CompetencyRef,
    CriticalError,
    EvidenceGate,
    LearnerBeliefSnapshot,
    SourceAffordance,
    SourceAffordanceMap,
    SourceProvenance,
)


class EpisodeInputDeclineReason(StrEnum):
    STALE_SELECTION = "stale_selection"
    UNKNOWN_SELECTION_REF = "unknown_selection_ref"
    MISSING_REQUIRED_EVIDENCE = "missing_required_evidence"
    MISSING_CRITICAL_SAFETY = "missing_critical_safety"
    INVALID_SOURCE_PROVENANCE = "invalid_source_provenance"
    MISSING_GROUNDED_AFFORDANCE = "missing_grounded_affordance"


@dataclass(frozen=True, slots=True)
class EpisodeInputDeclined:
    reason: EpisodeInputDeclineReason
    refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EpisodeInputs:
    competency: CompetencyContract
    source_map: SourceAffordanceMap
    belief: LearnerBeliefSnapshot


_MISSION_ACTIONS: dict[CognitiveMission, str] = {
    CognitiveMission.RECOGNIZE: "identify",
    CognitiveMission.RECONSTRUCT: "reconstruct",
    CognitiveMission.INTERPRET: "interpret",
    CognitiveMission.DECIDE: "decide",
    CognitiveMission.EXPLAIN: "explain",
    CognitiveMission.PRODUCE: "produce",
}
_SOURCE_ACTIONS: dict[SourceFunction, str] = {
    SourceFunction.ENUMERATE: "enumerate",
    SourceFunction.PROCEDURE: "follow_procedure",
    SourceFunction.QUANTIFY: "calculate",
    SourceFunction.CONTRAST: "compare",
    SourceFunction.VARY: "vary_input",
    SourceFunction.EXPLORE: "explore",
    SourceFunction.LOCATE: "locate",
    SourceFunction.ASSESS: "evaluate",
}
_PRESERVE_ACTIONS: dict[MustPreserveKind, str] = {
    MustPreserveKind.FACT: "inspect_fact",
    MustPreserveKind.SAFETY_RULE: "apply_safety_rule",
    MustPreserveKind.PROCEDURE_STEP: "follow_procedure",
    MustPreserveKind.CONSTRAINT: "apply_constraint",
    MustPreserveKind.CRITERION: "evaluate",
}
_SELECTABLE_ACTIONS: dict[SelectableKind, str] = {
    SelectableKind.CASE: "resolve_case",
    SelectableKind.COMMON_ERROR: "diagnose_error",
    SelectableKind.DECISION: "decide",
    SelectableKind.CONTRAST: "compare",
    SelectableKind.WORKED_EXAMPLE: "inspect_example",
    SelectableKind.REPRESENTATION_HINT: "inspect_reference",
}
_PRESENTATION_ACTIONS: dict[Presentation, str] = {
    Presentation.TEXT: "inspect_text",
    Presentation.IMAGE: "inspect_image",
    Presentation.AUDIO: "inspect_audio",
    Presentation.VIDEO: "inspect_video",
    Presentation.TABLE: "inspect_table",
    Presentation.CHART: "interpret_chart",
    Presentation.DIAGRAM: "inspect_diagram",
    Presentation.SIMULATION: "practice_scenario",
}


def _digest(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _plain_mapping(value: Mapping[str, Any] | object | None) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _selected_atoms(
    pack: NodeKnowledgePack, selection: RuntimeKnowledgeSelection
) -> tuple[tuple[MustPreserveAtom, ...], tuple[SelectableAtom, ...]] | EpisodeInputDeclined:
    if selection.pack_hash != pack.canonical_hash:
        return EpisodeInputDeclined(EpisodeInputDeclineReason.STALE_SELECTION)
    preserve = {item.atom_id: item for item in pack.must_preserve}
    selectable = {item.atom_id: item for item in pack.selectable}
    unknown = sorted(set(selection.atom_ids) - set(preserve) - set(selectable))
    if unknown:
        return EpisodeInputDeclined(
            EpisodeInputDeclineReason.UNKNOWN_SELECTION_REF, tuple(unknown)
        )
    return (
        tuple(preserve[ref] for ref in selection.atom_ids if ref in preserve),
        tuple(selectable[ref] for ref in selection.atom_ids if ref in selectable),
    )


def _evidence_gates(
    pack: NodeKnowledgePack,
    selection: RuntimeKnowledgeSelection,
    node: Mapping[str, Any],
) -> tuple[EvidenceGate, ...] | EpisodeInputDeclined:
    specs = {item.evidence_id: item for item in pack.evidence_specs}
    unknown = sorted(set(selection.evidence_ids) - set(specs))
    if unknown:
        return EpisodeInputDeclined(
            EpisodeInputDeclineReason.UNKNOWN_SELECTION_REF, tuple(unknown)
        )
    atoms = {
        item.atom_id: item for item in (*pack.must_preserve, *pack.selectable)
    }
    evidence_contracts = _plain_mapping(node.get("evidence_contracts"))
    gates: list[EvidenceGate] = []
    missing: list[str] = []
    for evidence_id in selection.evidence_ids:
        spec = specs[evidence_id]
        raw = _plain_mapping(evidence_contracts.get(evidence_id))
        oracle_ref = str(raw.get("oracle_ref") or "").strip()
        evidence_type = str(raw.get("evidence_type") or "").strip()
        if not oracle_ref or not evidence_type:
            if spec.required:
                missing.append(evidence_id)
            continue
        source_refs = tuple(
            sorted(
                {
                    source_ref
                    for atom_ref in spec.atom_refs
                    for source_ref in atoms[atom_ref].sources
                }
            )
        )
        gates.append(
            EvidenceGate(
                gate_id=evidence_id,
                evidence_type=evidence_type,
                oracle_ref=oracle_ref,
                source_refs=source_refs,
                minimum_score=raw.get("minimum_score"),
                required=spec.required,
            )
        )
    if missing:
        return EpisodeInputDeclined(
            EpisodeInputDeclineReason.MISSING_REQUIRED_EVIDENCE,
            tuple(sorted(missing)),
        )
    # A required pack evidence item cannot silently disappear from a forged selection.
    omitted = sorted(
        item.evidence_id
        for item in pack.evidence_specs
        if item.required and item.evidence_id not in selection.evidence_ids
    )
    if omitted:
        return EpisodeInputDeclined(
            EpisodeInputDeclineReason.MISSING_REQUIRED_EVIDENCE, tuple(omitted)
        )
    return tuple(gates)


def _affordances(
    pack: NodeKnowledgePack,
    invariant_atoms: tuple[MustPreserveAtom, ...],
    selectable_atoms: tuple[SelectableAtom, ...],
) -> tuple[SourceAffordance, ...]:
    base_actions = {
        _MISSION_ACTIONS[pack.objective.mission],
        *(_SOURCE_ACTIONS[item] for item in pack.objective.source_functions),
    }
    values: list[SourceAffordance] = []
    for atom in invariant_atoms:
        values.append(
            SourceAffordance(
                affordance_id=f"atom:{atom.atom_id}",
                kind=atom.kind.value,
                source_refs=tuple(sorted(atom.sources)),
                supports_actions=tuple(
                    sorted(base_actions | {_PRESERVE_ACTIONS[atom.kind]})
                ),
                fidelity="exact",
            )
        )
    for atom in selectable_atoms:
        presentation_actions = {
            _PRESENTATION_ACTIONS[item] for item in atom.presentations
        }
        values.append(
            SourceAffordance(
                affordance_id=f"atom:{atom.atom_id}",
                kind=atom.kind.value,
                source_refs=tuple(sorted(atom.sources)),
                supports_actions=tuple(
                    sorted(
                        base_actions
                        | presentation_actions
                        | {_SELECTABLE_ACTIONS[atom.kind]}
                    )
                ),
                fidelity="derived",
            )
        )
    return tuple(values)


def _belief(
    profile_bucket: Mapping[str, Any], node_state: Mapping[str, Any]
) -> LearnerBeliefSnapshot:
    mastery = max(0.0, min(1.0, float(node_state.get("mastery") or 0.0)))
    confidence = max(0.0, min(1.0, float(node_state.get("confidence") or 0.0)))
    raw_error = str(node_state.get("last_error_kind") or "").strip()
    errors = (raw_error,) if raw_error else ()
    hints_used = max(0, int(node_state.get("hints_used") or 0))
    experience_level = str(profile_bucket.get("experience_level") or "unknown").strip()
    bounded = {
        "confidence": confidence,
        "errors": errors,
        "experience_level": experience_level,
        "hints_used": hints_used,
        "mastery": mastery,
        "scaffold_band": str(node_state.get("scaffold_band") or "neutral"),
    }
    return LearnerBeliefSnapshot(
        mastery=mastery,
        confidence=confidence,
        recent_error_kinds=errors,
        hints_used=hints_used,
        experience_level=experience_level,
        state_digest=_digest(bounded),
    )


def episode_inputs_from_selection(
    pack: NodeKnowledgePack,
    selection: RuntimeKnowledgeSelection,
    *,
    node: Mapping[str, Any],
    profile_bucket: Mapping[str, Any] | None = None,
    node_state: Mapping[str, Any] | None = None,
) -> EpisodeInputs | EpisodeInputDeclined:
    """Project a frozen selection into grounded episode contracts or decline.

    ``node.evidence_contracts`` is part of the server-owned competency constitution,
    not a generated experience artifact.  Each required evidence id must resolve to an
    existing ``evidence_type`` and ``oracle_ref`` there; absence always declines.
    """

    selected = _selected_atoms(pack, selection)
    if isinstance(selected, EpisodeInputDeclined):
        return selected
    invariant_atoms, selectable_atoms = selected
    if not invariant_atoms and not selectable_atoms:
        return EpisodeInputDeclined(
            EpisodeInputDeclineReason.MISSING_GROUNDED_AFFORDANCE
        )

    declared_source_refs = {item.ref_id: item for item in pack.source_refs}
    selected_ref_ids = tuple(item.ref_id for item in selection.source_refs)
    unknown_sources = sorted(set(selected_ref_ids) - set(declared_source_refs))
    if unknown_sources:
        return EpisodeInputDeclined(
            EpisodeInputDeclineReason.UNKNOWN_SELECTION_REF, tuple(unknown_sources)
        )
    expected_sources = {
        ref
        for atom in (*invariant_atoms, *selectable_atoms)
        for ref in atom.sources
    }
    if expected_sources != set(selected_ref_ids):
        return EpisodeInputDeclined(
            EpisodeInputDeclineReason.UNKNOWN_SELECTION_REF,
            tuple(sorted(expected_sources.symmetric_difference(selected_ref_ids))),
        )

    try:
        provenance = {
            item.ref_id: SourceProvenance(
                document_id=item.document_id,
                origin_ref=item.ref_id,
                revision=item.source_revision,
                locator=item.locator,
                content_digest=item.excerpt_hash,
            )
            for item in selection.source_refs
        }
    except ValueError:
        return EpisodeInputDeclined(
            EpisodeInputDeclineReason.INVALID_SOURCE_PROVENANCE,
            tuple(sorted(selected_ref_ids)),
        )

    gates = _evidence_gates(pack, selection, node)
    if isinstance(gates, EpisodeInputDeclined):
        return gates
    gate_sources = {ref for gate in gates for ref in gate.source_refs}
    if not gate_sources.issubset(provenance):
        return EpisodeInputDeclined(
            EpisodeInputDeclineReason.UNKNOWN_SELECTION_REF,
            tuple(sorted(gate_sources - set(provenance))),
        )

    criticality = str(node.get("criticality") or "recommended").casefold()
    if criticality not in {"critical", "recommended", "contextual"}:
        criticality = "recommended"
    critical_atoms = tuple(item for item in invariant_atoms if item.critical)
    if criticality == "critical" and not critical_atoms:
        return EpisodeInputDeclined(
            EpisodeInputDeclineReason.MISSING_CRITICAL_SAFETY
        )
    critical_errors = tuple(
        CriticalError(
            error_id=f"violate:{atom.atom_id}",
            description=atom.text,
            source_refs=tuple(sorted(atom.sources)),
            recovery_state=f"remediate:{atom.atom_id}",
        )
        for atom in critical_atoms
    )
    required_fact_refs = tuple(
        sorted(
            {
                ref
                for atom in (*invariant_atoms, *selectable_atoms)
                for ref in atom.sources
            }
        )
    )
    competency = CompetencyContract(
        competency_id=pack.objective.objective_id,
        version=pack.objective.objective_version,
        domain=str(node.get("domain") or f"mission:{pack.objective.mission.value}"),
        outcome=str(node.get("outcome") or pack.title),
        criticality=criticality,
        required_fact_refs=required_fact_refs,
        # SelectableAtom.prereqs order knowledge atoms; they are not competency refs.
        prerequisite_refs=(),
        evidence_gates=gates,
        critical_errors=critical_errors,
        mastery_policy_ref=str(
            node.get("mastery_policy_ref") or "mastery:node-threshold/v1"
        ),
    )
    affordances = _affordances(pack, invariant_atoms, selectable_atoms)
    map_payload = {
        "competency_id": competency.competency_id,
        "competency_version": competency.version,
        "pack_hash": selection.pack_hash,
        "selection_hash": selection.selection_hash,
        "sources": {
            key: value.model_dump(mode="json") for key, value in provenance.items()
        },
        "affordances": [item.model_dump(mode="json") for item in affordances],
    }
    source_map = SourceAffordanceMap(
        map_id=f"knowledge-selection:{pack.node_id}",
        version=pack.objective.objective_version,
        competency_ref=CompetencyRef(
            competency_id=competency.competency_id, version=competency.version
        ),
        source_refs=provenance,
        affordances=affordances,
        map_digest=_digest(map_payload),
    )
    return EpisodeInputs(
        competency=competency,
        source_map=source_map,
        belief=_belief(
            _plain_mapping(profile_bucket), _plain_mapping(node_state)
        ),
    )


__all__ = [
    "EpisodeInputDeclineReason",
    "EpisodeInputDeclined",
    "EpisodeInputs",
    "episode_inputs_from_selection",
]
