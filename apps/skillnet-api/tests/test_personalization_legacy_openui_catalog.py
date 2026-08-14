from dataclasses import replace

import pytest

from src.personalization.legacy_openui_catalog import (
    LEGACY_OPENUI_POLICIES,
    LegacyOpenUICatalogDrift,
    adapt_legacy_openui_catalog,
)
from src.personalization.plan import (
    AccessibilityCapability,
    CognitiveMission,
    Presentation,
    ProducerKind,
)
from src.render.kit import ComponentSpec, UI_KIT, UIKit


def test_every_openui_component_has_an_explicit_policy() -> None:
    assert set(LEGACY_OPENUI_POLICIES) == set(UI_KIT.names)
    assert all(
        (policy.descriptor is None) != (policy.exclusion_reason is None)
        for policy in LEGACY_OPENUI_POLICIES.values()
    )


def test_adapter_is_deterministic_and_does_not_mutate_live_kit() -> None:
    names_before = UI_KIT.names

    first = adapt_legacy_openui_catalog()
    second = adapt_legacy_openui_catalog()

    assert first == second
    assert first is not second
    assert UI_KIT.names == names_before
    assert [item.component_id for item in first] == [
        "StepSequence",
        "Table",
        "CodeBlock",
        "Chart",
        "QuizItem",
        "BeforeAfter",
        "DragOrder",
        "AudioExplanation",
        "PronunciationExercise",
        "Flashcard",
        "HintReveal",
        "DidactGlossary",
        "DidactTimeline",
        "DidactWorkedExample",
        "LearningExperience",
        "DidactActivity",
    ]


def test_structural_and_supporting_blocks_are_not_planning_candidates() -> None:
    adapted_ids = {item.component_id for item in adapt_legacy_openui_catalog()}

    assert {"Stack", "Card", "TextContent", "Callout", "Markdown"}.isdisjoint(
        adapted_ids
    )
    assert LEGACY_OPENUI_POLICIES["Markdown"].exclusion_reason is not None


def test_legacy_capabilities_are_honest_about_richness_and_producer() -> None:
    catalog = {item.component_id: item for item in adapt_legacy_openui_catalog()}

    assert catalog["Chart"].missions == frozenset({CognitiveMission.INTERPRET})
    assert catalog["Chart"].presentations == frozenset({Presentation.CHART})
    assert "numeric_series" in catalog["Chart"].requirements

    assert catalog["DragOrder"].presentations == frozenset({Presentation.TEXT})
    assert catalog["DragOrder"].producer_kind is ProducerKind.ASSESSMENT
    assert AccessibilityCapability.KEYBOARD in catalog["DragOrder"].accessibility
    assert (
        AccessibilityCapability.NO_DRAG_ALTERNATIVE
        not in catalog["DragOrder"].accessibility
    )

    assert catalog["AudioExplanation"].producer_kind is ProducerKind.MEDIA
    assert catalog["PronunciationExercise"].missions == frozenset(
        {CognitiveMission.PRODUCE}
    )
    assert catalog["PronunciationExercise"].requirements == frozenset(
        {"tts_service", "microphone"}
    )


def test_new_or_removed_openui_component_causes_explicit_drift_failure() -> None:
    added = UIKit(
        components=UI_KIT.components
        + (ComponentSpec(name="FutureLab", purpose="test", props=()),)
    )
    removed = UIKit(
        components=tuple(
            component for component in UI_KIT.components if component.name != "HintReveal"
        )
    )

    with pytest.raises(LegacyOpenUICatalogDrift, match="FutureLab"):
        adapt_legacy_openui_catalog(added)
    with pytest.raises(LegacyOpenUICatalogDrift, match="HintReveal"):
        adapt_legacy_openui_catalog(removed)


def test_duplicate_component_names_are_rejected_before_adapting() -> None:
    duplicate = UIKit(components=UI_KIT.components + (replace(UI_KIT.components[0]),))

    with pytest.raises(LegacyOpenUICatalogDrift, match="duplicate"):
        adapt_legacy_openui_catalog(duplicate)
