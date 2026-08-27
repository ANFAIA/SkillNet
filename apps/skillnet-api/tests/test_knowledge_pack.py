from __future__ import annotations

import pytest
from pydantic import ValidationError
from types import SimpleNamespace

from src.knowledge_pack import (
    EvidenceSpec,
    GenerableSlot,
    MissingData,
    MissingDataArea,
    MustPreserveAtom,
    MustPreserveKind,
    NodeKnowledgePack,
    PackProvenance,
    PackStatus,
    SelectableAtom,
    SelectableKind,
    SelectionDeclineReason,
    SelectionDeclined,
    SelectionRequest,
    SourceRef,
    render_markdown,
    select_knowledge,
)
from src.personalization.plan import (
    CognitiveMission,
    LearningObjective,
    Presentation,
    SourceFunction,
)
from src.knowledge_pack.runtime_selection import select_runtime_knowledge

HASH_A = "a" * 64
HASH_B = "b" * 64


def _pack(**changes: object) -> NodeKnowledgePack:
    values: dict[str, object] = {
        "status": PackStatus.READY,
        "node_id": "take-order",
        "title": "Tomar una comanda",
        "objective": LearningObjective(
            objective_id="take-order",
            objective_version=2,
            mission=CognitiveMission.DECIDE,
            source_functions=frozenset({SourceFunction.PROCEDURE}),
            required_fact_refs=("fact:allergen",),
            required_safety_refs=("safety:allergen",),
        ),
        "source_refs": (
            SourceRef(
                ref_id="manual.allergens",
                document_id="manual-sala",
                heading_path=("Sala", "Alergenos"),
                locator="p. 34",
                excerpt_hash=HASH_A,
                source_revision="rev-4",
            ),
        ),
        "evidence_specs": (
            EvidenceSpec(
                evidence_id="allergen-marked",
                description="Marca el alérgeno antes de enviar.",
                atom_refs=("safety.allergen",),
            ),
        ),
        "must_preserve": (
            MustPreserveAtom(
                atom_id="safety.allergen",
                kind=MustPreserveKind.SAFETY_RULE,
                text="El alérgeno se registra en la línea del plato.",
                sources=("manual.allergens",),
                evidence=("allergen-marked",),
                critical=True,
            ),
        ),
        "selectable": (
            SelectableAtom(
                atom_id="case.allergy",
                kind=SelectableKind.CASE,
                text="Una comensal comunica una alergia al pedir.",
                sources=("manual.allergens",),
                missions=(CognitiveMission.DECIDE,),
                presentations=(Presentation.SIMULATION,),
                evidence=("allergen-marked",),
                tags=("allergen",),
                prereqs=("safety.allergen",),
            ),
            SelectableAtom(
                atom_id="contrast.allergy",
                kind=SelectableKind.CONTRAST,
                text="Compara una comanda segura con otra insegura.",
                sources=("manual.allergens",),
                missions=(CognitiveMission.DECIDE,),
                presentations=(Presentation.TABLE,),
                tags=("allergen",),
            ),
        ),
        "generable_slots": (
            GenerableSlot(
                slot_id="example.order",
                purpose="Ejemplo de comanda ficticia.",
                allowed_atom_refs=("safety.allergen", "case.allergy"),
                forbidden_claims=("No inventar políticas de devolución.",),
                max_items=2,
            ),
        ),
        "missing_data": (),
        "provenance": PackProvenance(
            node_id="take-order",
            schema_version=2,
            source_bundle_hash=HASH_A,
            semantic_hash=HASH_B,
            generator="knowledge-pack-generator/1",
            reviewer="reviewer-42",
        ),
    }
    values.update(changes)
    return NodeKnowledgePack(**values)


def test_pack_is_strict_frozen_and_cross_reference_validated() -> None:
    pack = _pack()

    with pytest.raises(ValidationError, match="lesson_body|Extra inputs"):
        NodeKnowledgePack(**pack.model_dump(), lesson_body="No debe entrar")
    with pytest.raises(ValidationError, match="frozen"):
        pack.title = "Otra cosa"  # type: ignore[misc]
    with pytest.raises(ValidationError, match="unknown sources"):
        _pack(
            must_preserve=(
                MustPreserveAtom(
                    atom_id="safety.allergen",
                    kind=MustPreserveKind.SAFETY_RULE,
                    text="Regla.",
                    sources=("missing.source",),
                ),
            )
        )


def test_pack_rejects_unknown_evidence_slots_and_prerequisite_cycles() -> None:
    with pytest.raises(ValidationError, match="unknown evidence"):
        _pack(
            must_preserve=(
                MustPreserveAtom(
                    atom_id="safety.allergen",
                    kind=MustPreserveKind.SAFETY_RULE,
                    text="Regla.",
                    sources=("manual.allergens",),
                    evidence=("missing-evidence",),
                ),
            )
        )
    with pytest.raises(ValidationError, match="cycle"):
        _pack(
            selectable=(
                SelectableAtom(
                    atom_id="case.a",
                    kind=SelectableKind.CASE,
                    text="Caso A.",
                    sources=("manual.allergens",),
                    prereqs=("case.b",),
                ),
                SelectableAtom(
                    atom_id="case.b",
                    kind=SelectableKind.CASE,
                    text="Caso B.",
                    sources=("manual.allergens",),
                    prereqs=("case.a",),
                ),
            )
            ,
            generable_slots=(
                GenerableSlot(
                    slot_id="example.order",
                    purpose="Ejemplo.",
                    allowed_atom_refs=("safety.allergen", "case.a"),
                ),
            ),
        )
    with pytest.raises(ValidationError, match="unknown atoms"):
        _pack(
            generable_slots=(
                GenerableSlot(
                    slot_id="example.order",
                    purpose="Ejemplo.",
                    allowed_atom_refs=("not-there",),
                ),
            )
        )


def test_hash_and_markdown_are_deterministic_and_markdown_is_derived() -> None:
    pack = _pack()

    assert pack.canonical_hash == _pack().canonical_hash
    first = render_markdown(pack)
    second = render_markdown(pack)
    assert first == second
    assert f"canonical_hash: {pack.canonical_hash}" in first
    assert "# Tomar una comanda" in first
    assert "## Debe conservarse" in first
    assert "## Opciones de adaptación" in first
    assert "lesson_body" not in first


def test_selector_preserves_invariants_required_evidence_and_prerequisites() -> None:
    result = select_knowledge(
        _pack(),
        SelectionRequest(
            mission=CognitiveMission.DECIDE,
            presentations=(Presentation.SIMULATION,),
            required_evidence_ids=("allergen-marked",),
            max_selectable_atoms=1,
        ),
    )

    assert not isinstance(result, SelectionDeclined)
    assert [item.atom_id for item in result.invariant_atoms] == ["safety.allergen"]
    assert [item.atom_id for item in result.selectable_atoms] == ["case.allergy"]
    assert result.evidence_ids == ("allergen-marked",)
    assert result.generable_slot_ids == ("example.order",)
    assert result == select_knowledge(
        _pack(),
        SelectionRequest(
            mission=CognitiveMission.DECIDE,
            presentations=(Presentation.SIMULATION,),
            required_evidence_ids=("allergen-marked",),
            max_selectable_atoms=1,
        ),
    )


def test_runtime_adapter_turns_a_ready_pack_into_bounded_openui_context() -> None:
    result = select_runtime_knowledge(
        _pack().canonical_payload(),
        profile=SimpleNamespace(
            role_title="Camarero",
            sector="Hostelería",
            experience_level="some",
            preset="standard",
            format_vector={},
            learning_preferences={"presentation": "interactive"},
            nodes_completed=4,
        ),
        node_state=SimpleNamespace(scaffold_band="neutral", last_error_kind=None),
        accessibility={},
        base_density=3,
    )

    assert result is not None
    assert result.atom_ids == ("safety.allergen", "case.allergy")
    assert tuple(item.ref_id for item in result.source_refs) == ("manual.allergens",)
    assert "El alérgeno se registra" in result.source_context
    assert "Una comensal comunica" in result.source_context
    assert "No inventar políticas" in result.source_context
    assert len(result.selection_hash) == 64


def test_the_dossier_keeps_its_internal_refs_out_of_the_copyable_prefix() -> None:
    """The other half of the leak of 2026-08-27.

    Every point of the dossier used to READ ``- [must.atom:1] texto``, so a model copying a
    point copied the marker with it and a learner saw the id on screen. The reference now
    trails the prose, and it is still there — the pipeline needs it, and this test is what
    keeps someone from "cleaning it up" in either direction.

    It also pins the fingerprint the runtime render gate relies on: whatever this function
    writes must be recognizable as server scaffolding by
    ``agents.runtime.nodes.leaked_scaffolding_markers``, which is what keeps it off a
    learner's screen when generation fails.
    """
    from src.agents.runtime.nodes import leaked_scaffolding_markers

    result = select_runtime_knowledge(
        _pack().canonical_payload(),
        profile=None,
        node_state=None,
        accessibility={},
        base_density=3,
    )

    assert result is not None
    points = [
        line for line in result.source_context.splitlines() if line.startswith("- ")
    ]
    assert points
    for line in points:
        assert not line.startswith("- ["), line
    assert "(ref safety.allergen)" in result.source_context
    assert leaked_scaffolding_markers(result.source_context)


def test_runtime_adapter_declines_a_pack_that_still_requires_review() -> None:
    payload = _pack(status=PackStatus.REVIEW_REQUIRED).canonical_payload()

    assert select_runtime_knowledge(
        payload,
        profile=None,
        node_state=None,
        accessibility={},
        base_density=3,
    ) is None


def test_selector_declines_safely_for_missing_blocking_data_or_evidence() -> None:
    with_missing_data = _pack(
        missing_data=(
            MissingData(
                data_id="missing-menu-state",
                description="No hay modelo de estados del TPV.",
                affects=(MissingDataArea.SIMULATION, MissingDataArea.EVIDENCE),
                blocking=True,
                fallback="Usar un caso escrito sin afirmar manejo del TPV.",
            ),
        )
    )
    blocked = select_knowledge(
        with_missing_data,
        SelectionRequest(
            mission=CognitiveMission.DECIDE,
            requested_areas=(MissingDataArea.SIMULATION,),
        ),
    )
    assert blocked == SelectionDeclined(
        reason=SelectionDeclineReason.BLOCKING_DATA_MISSING,
        blocking_ids=("missing-menu-state",),
    )

    evidence_gap = _pack(
        missing_data=(
            MissingData(
                data_id="missing-observation",
                description="La evidencia requerida no está fundamentada.",
                affects=(MissingDataArea.EVIDENCE,),
                blocking=True,
                fallback="human_review",
            ),
        )
    )
    assert select_knowledge(
        evidence_gap, SelectionRequest(mission=CognitiveMission.DECIDE)
    ) == SelectionDeclined(
        reason=SelectionDeclineReason.BLOCKING_DATA_MISSING,
        blocking_ids=("missing-observation",),
    )

    unsupported = select_knowledge(
        _pack(),
        SelectionRequest(
            mission=CognitiveMission.DECIDE,
            required_evidence_ids=("not-declared",),
        ),
    )
    assert unsupported == SelectionDeclined(
        reason=SelectionDeclineReason.REQUIRED_EVIDENCE_UNSATISFIED,
        unsatisfied_evidence_ids=("not-declared",),
    )


def test_selector_declines_before_using_a_pack_not_ready_for_review() -> None:
    result = select_knowledge(
        _pack(status=PackStatus.REVIEW_REQUIRED),
        SelectionRequest(mission=CognitiveMission.DECIDE),
    )

    assert result == SelectionDeclined(reason=SelectionDeclineReason.PACK_NOT_READY)
