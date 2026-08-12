from __future__ import annotations

import pytest

from src.personalization.didact_catalog import load_didact_catalog
from src.personalization.didact_descriptors import (
    DidactExposureError,
    export_didact_descriptors,
    openui_names_for_shortlist,
)
from src.personalization.plan import ProducerKind
from src.render.prompt_slice import build_didact_prompt_slice


def test_descriptor_export_covers_the_complete_inventory_deterministically() -> None:
    first = export_didact_descriptors()
    second = export_didact_descriptors()

    assert first == second
    assert len(first) == 34
    assert {item.component_id for item in first} == set(load_didact_catalog().by_type_id)
    assert all(item.missions for item in first)
    assert all(item.source_functions for item in first)
    assert all(item.presentations for item in first)


def test_descriptor_projection_retains_semantic_families_and_host_requirements() -> None:
    descriptors = {item.component_id: item for item in export_didact_descriptors()}

    assert descriptors["didact.simulation-lab"].producer_kind is ProducerKind.SIMULATION
    assert "simulation" in descriptors["didact.simulation-lab"].requirements
    assert descriptors["didact.code-exercise"].producer_kind is ProducerKind.ASSESSMENT
    assert {"evaluation", "execution"} <= descriptors["didact.code-exercise"].requirements
    assert descriptors["didact.interactive-media"].producer_kind is ProducerKind.MEDIA
    assert "assets" in descriptors["didact.interactive-media"].requirements


def test_planner_can_see_all_types_but_emittable_projection_is_explicitly_smaller() -> None:
    assert len(export_didact_descriptors()) == 34
    assert {item.component_id for item in export_didact_descriptors(emittable_only=True)} == {
        "didact.flashcard",
        "didact.hint-reveal",
        "didact.glossary-term",
        "didact.timeline-steps",
        "didact.worked-example",
        "didact.rubric",
        "didact.data-explorer",
        "didact.self-explanation-prompt",
        "didact.concept-map",
        "didact.drawing-response",
        "didact.equation-workbench",
        "didact.evidence-annotation",
        "didact.measurement-lab",
    }


def test_openui_boundary_translates_only_enabled_host_ready_types() -> None:
    assert openui_names_for_shortlist(
        ["didact.hint-reveal", "didact.flashcard", "didact.hint-reveal"]
    ) == ("HintReveal", "Flashcard")
    assert openui_names_for_shortlist(
        [
            "didact.glossary-term",
            "didact.timeline-steps",
            "didact.worked-example",
        ]
    ) == (
        "DidactGlossary",
        "DidactTimeline",
        "DidactWorkedExample",
    )

    with pytest.raises(DidactExposureError, match="didact.simulation-lab"):
        openui_names_for_shortlist(["didact.simulation-lab"])
    assert openui_names_for_shortlist(["didact.self-explanation-prompt"]) == (
        "DidactActivity",
    )
    with pytest.raises(DidactExposureError, match="unknown Didact"):
        openui_names_for_shortlist(["didact.missing"])


def test_didact_prompt_slice_contains_only_shortlisted_schema_and_safe_shell() -> None:
    scope = build_didact_prompt_slice(["didact.flashcard"])

    assert "Flashcard" in scope.included_component_ids
    assert "HintReveal" not in scope.included_component_ids
    assert "Flashcard(" in scope.prompt
    assert "HintReveal(" not in scope.prompt

    with pytest.raises(DidactExposureError):
        build_didact_prompt_slice(["didact.code-exercise"])
