"""Resolve a validated pack into bounded source context for live OpenUI generation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from src.knowledge_pack.contracts import MissingDataArea, NodeKnowledgePack, SourceRef
from src.knowledge_pack.configured_generator import GENERATOR_VERSION
from src.knowledge_pack.selector import SelectionRequest, SelectionResult, select_knowledge
from src.personalization.plan import Presentation
from src.personalization.projection import project_runtime_signals
from src.repositories.node_knowledge_pack_repo import NodeKnowledgePackRepository


@dataclass(frozen=True)
class RuntimeKnowledgeSelection:
    pack_hash: str
    selection_hash: str
    cache_fragment: str
    source_context: str
    atom_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    source_refs: tuple[SourceRef, ...]
    # Server-only canonical payload retained so the adaptive branch can project the same
    # frozen selection into episode contracts without fetching or selecting a second time.
    pack_payload: dict[str, Any]


def _selection_hash(result: SelectionResult) -> str:
    value = {
        "pack_hash": result.pack_hash,
        "invariants": [item.atom_id for item in result.invariant_atoms],
        "selectable": [item.atom_id for item in result.selectable_atoms],
        "evidence": list(result.evidence_ids),
        "slots": list(result.generable_slot_ids),
        "selector_version": "runtime-selection/1",
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _render_context(pack: NodeKnowledgePack, result: SelectionResult) -> str:
    evidence = {item.evidence_id: item for item in pack.evidence_specs}
    slots = {item.slot_id: item for item in pack.generable_slots}
    lines = [
        "# Dossier pedagógico seleccionado",
        "",
        "Usa únicamente los hechos y posibilidades siguientes. Conserva todos los "
        "invariantes y no inventes reglas fuera del dossier.",
        "",
        "## Invariantes",
        "",
    ]
    for atom in result.invariant_atoms:
        lines.append(f"- [{atom.atom_id}] {atom.text}")
    if result.selectable_atoms:
        lines.extend(["", "## Material adaptable", ""])
        for atom in result.selectable_atoms:
            lines.append(f"- [{atom.atom_id}] {atom.text}")
    if result.evidence_ids:
        lines.extend(["", "## Evidencia que debe obtenerse", ""])
        for evidence_id in result.evidence_ids:
            lines.append(f"- [{evidence_id}] {evidence[evidence_id].description}")
    if result.generable_slot_ids:
        lines.extend(["", "## Espacios generables permitidos", ""])
        for slot_id in result.generable_slot_ids:
            slot = slots[slot_id]
            lines.append(f"- [{slot_id}] {slot.purpose}")
            for forbidden in slot.forbidden_claims:
                lines.append(f"  - No afirmar: {forbidden}")
    return "\n".join(lines).rstrip() + "\n"


def select_runtime_knowledge(
    payload: dict[str, Any],
    *,
    profile: Any | None,
    node_state: Any | None,
    accessibility: dict[str, Any] | None,
    base_density: int,
) -> RuntimeKnowledgeSelection | None:
    """Pure adapter. A decline means the caller must retain raw source context."""
    pack = NodeKnowledgePack.model_validate(payload)
    projection = project_runtime_signals(
        role_title=getattr(profile, "role_title", None),
        sector=getattr(profile, "sector", None),
        experience_level=getattr(profile, "experience_level", "unknown"),
        scaffold_band=getattr(node_state, "scaffold_band", None),
        preset=getattr(profile, "preset", "standard"),
        format_vector=dict(getattr(profile, "format_vector", None) or {}),
        accessibility=accessibility or {},
        learning_preferences=dict(
            getattr(profile, "learning_preferences", None) or {}
        ),
        nodes_completed=int(getattr(profile, "nodes_completed", 0) or 0),
        last_error_kind=getattr(node_state, "last_error_kind", None),
        base_density=base_density,
    )
    requested_areas: list[MissingDataArea] = []
    if Presentation.IMAGE in projection.declared_presentations:
        requested_areas.append(MissingDataArea.MEDIA)
    if Presentation.SIMULATION in projection.declared_presentations:
        requested_areas.append(MissingDataArea.SIMULATION)
    selected = select_knowledge(
        pack,
        SelectionRequest(
            mission=pack.objective.mission,
            presentations=projection.declared_presentations,
            requested_areas=tuple(requested_areas),
            max_selectable_atoms=max(1, min(6, int(projection.density))),
        ),
    )
    if not isinstance(selected, SelectionResult):
        return None
    selection_hash = _selection_hash(selected)
    selected_atoms = (*selected.invariant_atoms, *selected.selectable_atoms)
    selected_source_ids = {
        source_ref for atom in selected_atoms for source_ref in atom.sources
    }
    source_refs = tuple(
        source_ref
        for source_ref in sorted(pack.source_refs, key=lambda item: item.ref_id)
        if source_ref.ref_id in selected_source_ids
    )
    return RuntimeKnowledgeSelection(
        pack_hash=selected.pack_hash,
        selection_hash=selection_hash,
        cache_fragment=f"{selected.pack_hash}:{selection_hash}",
        source_context=_render_context(pack, selected),
        atom_ids=tuple(
            item.atom_id
            for item in (*selected.invariant_atoms, *selected.selectable_atoms)
        ),
        evidence_ids=selected.evidence_ids,
        source_refs=source_refs,
        pack_payload=pack.canonical_payload(),
    )


async def load_runtime_knowledge(
    db: Any,
    *,
    node: Any,
    course: Any,
    profile: Any | None,
    node_state: Any | None,
    accessibility: dict[str, Any] | None,
) -> RuntimeKnowledgeSelection | None:
    record = await NodeKnowledgePackRepository(db).find_ready_for_schema(
        node_id=node.id,
        schema_version=int(getattr(course, "schema_version", 1) or 1),
        generator_version=GENERATOR_VERSION,
    )
    if record is None:
        return None
    return select_runtime_knowledge(
        dict(record.pack_payload or {}),
        profile=profile,
        node_state=node_state,
        accessibility=accessibility,
        base_density=int(getattr(course, "intent_density", 3) or 3),
    )


__all__ = [
    "RuntimeKnowledgeSelection",
    "load_runtime_knowledge",
    "select_runtime_knowledge",
]
