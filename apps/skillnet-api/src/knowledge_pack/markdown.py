"""Deterministic Markdown projection of a :mod:`knowledge_pack` contract.

The projection is deliberately one-way: Markdown is review material, not an input
format for the runtime and not an executable lesson definition.
"""

from __future__ import annotations

from src.knowledge_pack.contracts import NodeKnowledgePack


def _line(value: str) -> str:
    """Keep a generated Markdown field on one predictable line."""

    return " ".join(value.splitlines()).strip()


def _source_list(refs: tuple[str, ...]) -> str:
    return ", ".join(f"`{ref}`" for ref in refs)


def render_markdown(pack: NodeKnowledgePack) -> str:
    """Render an audit-friendly, deterministic Markdown view of ``pack``."""

    lines = [
        "---",
        f"format: {pack.format}",
        f"node_id: {pack.node_id}",
        f"status: {pack.status.value}",
        f"canonical_hash: {pack.canonical_hash}",
        f"source_bundle_hash: {pack.provenance.source_bundle_hash}",
        f"semantic_hash: {pack.provenance.semantic_hash}",
        "---",
        "",
        f"# {_line(pack.title)}",
        "",
        "## Objetivo",
        "",
        _line(pack.objective.objective_id),
        "",
        "## Debe conservarse",
        "",
    ]
    for atom in sorted(pack.must_preserve, key=lambda item: item.atom_id):
        critical = " · crítico" if atom.critical else ""
        evidence = f" · evidencia: {_source_list(atom.evidence)}" if atom.evidence else ""
        lines.extend(
            [
                f"### `{atom.atom_id}` · {atom.kind.value}{critical}",
                "",
                _line(atom.text),
                "",
                f"Fuentes: {_source_list(atom.sources)}{evidence}",
                "",
            ]
        )

    lines.extend(["## Opciones de adaptación", ""])
    for atom in sorted(pack.selectable, key=lambda item: item.atom_id):
        details = []
        if atom.missions:
            details.append("misiones: " + ", ".join(item.value for item in atom.missions))
        if atom.presentations:
            details.append("presentaciones: " + ", ".join(item.value for item in atom.presentations))
        if atom.tags:
            details.append("etiquetas: " + ", ".join(atom.tags))
        lines.extend(
            [
                f"### `{atom.atom_id}` · {atom.kind.value}",
                "",
                _line(atom.text),
                "",
                f"Fuentes: {_source_list(atom.sources)}",
                f"Detalles: {' · '.join(details) if details else 'sin restricciones declaradas'}",
                "",
            ]
        )

    lines.extend(["## Evidencia", ""])
    for item in sorted(pack.evidence_specs, key=lambda value: value.evidence_id):
        required = "obligatoria" if item.required else "opcional"
        refs = _source_list(item.atom_refs) if item.atom_refs else "sin átomo fijado"
        lines.extend([f"- `{item.evidence_id}` ({required}): {_line(item.description)} — {refs}"])

    if pack.generable_slots:
        lines.extend(["", "## Generable dentro de límites", ""])
        for slot in sorted(pack.generable_slots, key=lambda item: item.slot_id):
            lines.append(
                f"- `{slot.slot_id}`: {_line(slot.purpose)} "
                f"(máximo {slot.max_items}; usa {_source_list(slot.allowed_atom_refs)})"
            )
    if pack.missing_data:
        lines.extend(["", "## Datos pendientes", ""])
        for item in sorted(pack.missing_data, key=lambda value: value.data_id):
            areas = ", ".join(area.value for area in item.affects)
            blocking = "bloqueante" if item.blocking else "no bloqueante"
            lines.append(
                f"- `{item.data_id}` ({blocking}; afecta: {areas}): "
                f"{_line(item.description)}. Fallback: {_line(item.fallback)}"
            )

    lines.extend(["", "## Fuentes", ""])
    for ref in sorted(pack.source_refs, key=lambda item: item.ref_id):
        heading = " › ".join(ref.heading_path) if ref.heading_path else "sin encabezado"
        lines.append(
            f"- `{ref.ref_id}`: documento `{ref.document_id}`, {heading}, "
            f"{_line(ref.locator)} (revisión `{ref.source_revision}`)"
        )
    return "\n".join(lines) + "\n"
