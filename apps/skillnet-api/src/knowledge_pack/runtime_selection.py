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


#: The literal headings :func:`_render_context` writes. Exported as constants because they
#: are the fingerprint of the **server prompt**: the runtime render gate greps generated
#: learner-facing text for them (``src/agents/runtime/nodes.py``,
#: ``leaked_scaffolding_markers``), and a detector that spelled the same strings out a
#: second time would drift from the emitter the first time a heading changed here.
DOSSIER_TITLE = "Dossier pedagógico seleccionado"

#: Section headings, in the order :func:`_render_context` emits them.
DOSSIER_SECTION_HEADINGS: tuple[str, ...] = (
    "Invariantes",
    "Material adaptable",
    "Evidencia que debe obtenerse",
    "Espacios generables permitidos",
)


def _point(text: str, ref_id: str) -> str:
    """One dossier point: the prose first, its internal reference **last**.

    The reference used to lead the line (``- [must.atom:1] texto``). A model that copied a
    point verbatim therefore copied the marker with it, and on 2026-08-27 a learner read
    ``[must.atom:1] Si el cliente dice que no le ha llegado la entrada...`` on screen as
    though it were the lesson. Trailing the reference keeps every bit of the traceability
    the pipeline needs — the id is still adjacent to its text for a human reading the
    prompt, and the authoring prompt receives ``allowed_source_refs`` as its own field
    (``services/activity_authoring.build_activity_authoring_prompts``), never by scraping
    this text — while making the copyable *prefix* of every line clean prose.
    """
    return f"- {text.strip()} (ref {ref_id})"


def _render_context(pack: NodeKnowledgePack, result: SelectionResult) -> str:
    evidence = {item.evidence_id: item for item in pack.evidence_specs}
    slots = {item.slot_id: item for item in pack.generable_slots}
    lines = [
        f"# {DOSSIER_TITLE}",
        "",
        "Usa únicamente los hechos y posibilidades siguientes. Conserva todos los "
        "invariantes y no inventes reglas fuera del dossier.",
        "",
        "Los títulos de este dossier y las referencias entre paréntesis (`ref ...`) son "
        "andamiaje interno del servidor: NO los copies en el texto que leerá el "
        "aprendiz.",
        "",
        f"## {DOSSIER_SECTION_HEADINGS[0]}",
        "",
    ]
    for atom in result.invariant_atoms:
        lines.append(_point(atom.text, atom.atom_id))
    if result.selectable_atoms:
        lines.extend(["", f"## {DOSSIER_SECTION_HEADINGS[1]}", ""])
        for atom in result.selectable_atoms:
            lines.append(_point(atom.text, atom.atom_id))
    if result.evidence_ids:
        lines.extend(["", f"## {DOSSIER_SECTION_HEADINGS[2]}", ""])
        for evidence_id in result.evidence_ids:
            lines.append(_point(evidence[evidence_id].description, evidence_id))
    if result.generable_slot_ids:
        lines.extend(["", f"## {DOSSIER_SECTION_HEADINGS[3]}", ""])
        for slot_id in result.generable_slot_ids:
            slot = slots[slot_id]
            lines.append(_point(slot.purpose, slot_id))
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
    "DOSSIER_SECTION_HEADINGS",
    "DOSSIER_TITLE",
    "RuntimeKnowledgeSelection",
    "load_runtime_knowledge",
    "select_runtime_knowledge",
]
