"""Deterministic, fail-closed selection from a node knowledge pack."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator

from src.knowledge_pack.contracts import (
    MissingDataArea,
    MustPreserveAtom,
    NodeKnowledgePack,
    SelectableAtom,
    _StrictFrozenModel,
    _identifier,
)
from src.personalization.plan import CognitiveMission, Presentation


class SelectionDeclineReason(StrEnum):
    PACK_NOT_READY = "pack_not_ready"
    BLOCKING_DATA_MISSING = "blocking_data_missing"
    REQUIRED_EVIDENCE_UNSATISFIED = "required_evidence_unsatisfied"


class SelectionRequest(_StrictFrozenModel):
    """Closed intent passed to the pure selector; no learner text crosses here."""

    mission: CognitiveMission
    presentations: tuple[Presentation, ...] = ()
    required_evidence_ids: tuple[str, ...] = ()
    requested_areas: tuple[MissingDataArea, ...] = ()
    max_selectable_atoms: int = Field(default=3, ge=0, le=12)

    @field_validator("required_evidence_ids")
    @classmethod
    def _validate_evidence_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        refs = tuple(_identifier(item) for item in value)
        if len(set(refs)) != len(refs):
            raise ValueError("must not contain duplicate references")
        return refs

    @field_validator("presentations", "requested_areas")
    @classmethod
    def _validate_unique_values(cls, value: tuple[object, ...]) -> tuple[object, ...]:
        if len(set(value)) != len(value):
            raise ValueError("must not contain duplicates")
        return value


class SelectionDeclined(_StrictFrozenModel):
    reason: SelectionDeclineReason
    blocking_ids: tuple[str, ...] = ()
    unsatisfied_evidence_ids: tuple[str, ...] = ()


class SelectionResult(_StrictFrozenModel):
    """A closed selection. Every result includes all invariants by construction."""

    pack_hash: str
    invariant_atoms: tuple[MustPreserveAtom, ...]
    selectable_atoms: tuple[SelectableAtom, ...]
    evidence_ids: tuple[str, ...]
    generable_slot_ids: tuple[str, ...]


def _blocking_missing(pack: NodeKnowledgePack, request: SelectionRequest) -> tuple[str, ...]:
    needed = set(request.requested_areas)
    # Safety and evidence gaps are never optional. Presentation-specific media or
    # simulation gaps only block when the caller actually requested those areas.
    needed.update({MissingDataArea.SAFETY, MissingDataArea.EVIDENCE})
    return tuple(
        item.data_id
        for item in sorted(pack.missing_data, key=lambda value: value.data_id)
        if item.blocking and needed.intersection(item.affects)
    )


def _candidate_matches(atom: SelectableAtom, request: SelectionRequest) -> bool:
    return (not atom.missions or request.mission in atom.missions) and (
        not atom.presentations
        or not request.presentations
        or bool(set(atom.presentations).intersection(request.presentations))
    )


def _prerequisite_closure(
    selected_ids: set[str], all_atoms: dict[str, MustPreserveAtom | SelectableAtom]
) -> set[str]:
    pending = list(selected_ids)
    while pending:
        atom = all_atoms[pending.pop()]
        if not isinstance(atom, SelectableAtom):
            continue
        for prerequisite in atom.prereqs:
            if prerequisite not in selected_ids:
                selected_ids.add(prerequisite)
                pending.append(prerequisite)
    return selected_ids


def select_knowledge(
    pack: NodeKnowledgePack, request: SelectionRequest
) -> SelectionResult | SelectionDeclined:
    """Select adaptation material without ever omitting required truth.

    A missing blocking prerequisite or unsupported required evidence returns a structured
    decline.  The caller must use its declared fallback instead of asking an LLM to fill
    the gap.
    """

    if pack.status.value != "ready":
        return SelectionDeclined(reason=SelectionDeclineReason.PACK_NOT_READY)

    blocking_ids = _blocking_missing(pack, request)
    if blocking_ids:
        return SelectionDeclined(
            reason=SelectionDeclineReason.BLOCKING_DATA_MISSING,
            blocking_ids=blocking_ids,
        )

    evidence_by_id = {item.evidence_id: item for item in pack.evidence_specs}
    required = set(request.required_evidence_ids)
    required.update(item.evidence_id for item in pack.evidence_specs if item.required)
    unknown_evidence = required - set(evidence_by_id)
    if unknown_evidence:
        return SelectionDeclined(
            reason=SelectionDeclineReason.REQUIRED_EVIDENCE_UNSATISFIED,
            unsatisfied_evidence_ids=tuple(sorted(unknown_evidence)),
        )

    all_atoms: dict[str, MustPreserveAtom | SelectableAtom] = {
        item.atom_id: item for item in (*pack.must_preserve, *pack.selectable)
    }
    selected_ids: set[str] = {item.atom_id for item in pack.must_preserve}
    for evidence_id in required:
        selected_ids.update(evidence_by_id[evidence_id].atom_refs)
    selected_ids = _prerequisite_closure(selected_ids, all_atoms)

    selected_selectable = {
        atom_id for atom_id in selected_ids if isinstance(all_atoms[atom_id], SelectableAtom)
    }
    candidates = [
        item
        for item in sorted(pack.selectable, key=lambda value: value.atom_id)
        if item.atom_id not in selected_ids and _candidate_matches(item, request)
    ]
    for item in candidates:
        if len(selected_selectable) >= request.max_selectable_atoms:
            break
        candidate_ids = _prerequisite_closure(selected_ids | {item.atom_id}, all_atoms)
        candidate_selectable = {
            atom_id
            for atom_id in candidate_ids
            if isinstance(all_atoms[atom_id], SelectableAtom)
        }
        if len(candidate_selectable) > request.max_selectable_atoms:
            continue
        selected_ids, selected_selectable = candidate_ids, candidate_selectable

    selected_evidence = {
        evidence_id
        for evidence_id, spec in evidence_by_id.items()
        if set(spec.atom_refs).issubset(selected_ids)
    }
    missing_evidence = required - selected_evidence
    if missing_evidence:
        return SelectionDeclined(
            reason=SelectionDeclineReason.REQUIRED_EVIDENCE_UNSATISFIED,
            unsatisfied_evidence_ids=tuple(sorted(missing_evidence)),
        )

    return SelectionResult(
        pack_hash=pack.canonical_hash,
        invariant_atoms=tuple(sorted(pack.must_preserve, key=lambda item: item.atom_id)),
        selectable_atoms=tuple(
            all_atoms[atom_id]
            for atom_id in sorted(selected_ids)
            if isinstance(all_atoms[atom_id], SelectableAtom)
        ),
        evidence_ids=tuple(sorted(selected_evidence)),
        generable_slot_ids=tuple(
            item.slot_id
            for item in sorted(pack.generable_slots, key=lambda value: value.slot_id)
            if set(item.allowed_atom_refs).issubset(selected_ids)
        ),
    )
