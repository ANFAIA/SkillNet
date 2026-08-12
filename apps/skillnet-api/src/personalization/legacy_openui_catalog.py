"""Pure shadow-planner adapter for the current OpenUI catalogue.

The live OpenUI catalogue remains the rendering and validation source of truth.  This
module adds a deliberately separate pedagogical projection for experiments: it does not
mutate ``UI_KIT``, generate prompts, or participate in production routing.

Every legacy component must have an explicit policy below.  Some entries are excluded
because they are structural or supporting blocks rather than complete learning
activities.  Keeping exclusions explicit makes catalogue drift fail loudly instead of
silently inventing capabilities for a newly added component.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.personalization.plan import (
    AccessibilityCapability,
    CognitiveMission,
    ComponentDescriptor,
    Presentation,
    ProducerKind,
    SourceFunction,
)
from src.render.kit import UI_KIT, UIKit


class LegacyOpenUICatalogDrift(ValueError):
    """The OpenUI kit and its explicit shadow-planning policies disagree."""


@dataclass(frozen=True, slots=True)
class LegacyComponentPolicy:
    """One explicit decision about a legacy OpenUI component."""

    descriptor: ComponentDescriptor | None = None
    exclusion_reason: str | None = None

    def __post_init__(self) -> None:
        if (self.descriptor is None) == (self.exclusion_reason is None):
            raise ValueError("declare exactly one of descriptor or exclusion_reason")
        if self.exclusion_reason is not None and not self.exclusion_reason.strip():
            raise ValueError("exclusion_reason must not be empty")


_STATIC_ACCESSIBILITY = frozenset(
    {
        AccessibilityCapability.KEYBOARD,
        AccessibilityCapability.SCREEN_READER,
        AccessibilityCapability.REDUCED_MOTION,
        AccessibilityCapability.NO_DRAG_ALTERNATIVE,
    }
)
_INTERACTIVE_ACCESSIBILITY = frozenset(
    {
        AccessibilityCapability.KEYBOARD,
        AccessibilityCapability.SCREEN_READER,
    }
)


def _descriptor(
    component_id: str,
    *,
    missions: frozenset[CognitiveMission],
    source_functions: frozenset[SourceFunction],
    presentations: frozenset[Presentation],
    producer_kind: ProducerKind,
    affordances: frozenset[str] = frozenset(),
    evidence_events: frozenset[str] = frozenset(),
    state_model_ref: str | None = None,
    requirements: frozenset[str] = frozenset(),
    accessibility: frozenset[AccessibilityCapability] = _STATIC_ACCESSIBILITY,
    rank: int = 100,
) -> LegacyComponentPolicy:
    return LegacyComponentPolicy(
        descriptor=ComponentDescriptor(
            component_id=component_id,
            version=1,
            missions=missions,
            source_functions=source_functions,
            presentations=presentations,
            producer_kind=producer_kind,
            affordances=affordances,
            evidence_events=evidence_events,
            state_model_ref=state_model_ref,
            requirements=requirements,
            accessibility=accessibility,
            rank=rank,
        )
    )


# This table is intentionally explicit rather than inferred from prop names or component
# names. OpenUI describes how to render a block; it does not contain enough information
# to infer what a learner can do with it or which producer must create its state.
LEGACY_OPENUI_POLICIES: dict[str, LegacyComponentPolicy] = {
    "Stack": LegacyComponentPolicy(exclusion_reason="structural root container"),
    "TextContent": LegacyComponentPolicy(
        exclusion_reason="supporting lead or transition, not a complete learning activity"
    ),
    "Card": LegacyComponentPolicy(exclusion_reason="structural grouping container"),
    "Callout": LegacyComponentPolicy(
        exclusion_reason="supporting invariant or warning, not a central learning activity"
    ),
    "StepSequence": _descriptor(
        "StepSequence",
        missions=frozenset({CognitiveMission.RECOGNIZE, CognitiveMission.RECONSTRUCT}),
        source_functions=frozenset({SourceFunction.PROCEDURE}),
        presentations=frozenset({Presentation.TEXT}),
        producer_kind=ProducerKind.CONTENT,
        affordances=frozenset({"inspect_ordered_steps"}),
        rank=10,
    ),
    "Table": _descriptor(
        "Table",
        missions=frozenset({CognitiveMission.RECOGNIZE, CognitiveMission.INTERPRET}),
        source_functions=frozenset(
            {SourceFunction.ENUMERATE, SourceFunction.QUANTIFY, SourceFunction.CONTRAST}
        ),
        presentations=frozenset({Presentation.TABLE}),
        producer_kind=ProducerKind.CONTENT,
        affordances=frozenset({"scan_rows", "compare_values"}),
        rank=10,
    ),
    "CodeBlock": _descriptor(
        "CodeBlock",
        missions=frozenset({CognitiveMission.RECOGNIZE, CognitiveMission.INTERPRET}),
        source_functions=frozenset({SourceFunction.PROCEDURE, SourceFunction.EXPLORE}),
        presentations=frozenset({Presentation.TEXT}),
        producer_kind=ProducerKind.CONTENT,
        affordances=frozenset({"inspect_code"}),
        requirements=frozenset({"source_code"}),
        rank=30,
    ),
    "Chart": _descriptor(
        "Chart",
        missions=frozenset({CognitiveMission.INTERPRET}),
        source_functions=frozenset({SourceFunction.QUANTIFY, SourceFunction.CONTRAST}),
        presentations=frozenset({Presentation.CHART}),
        producer_kind=ProducerKind.CONTENT,
        affordances=frozenset({"compare_values", "inspect_trend"}),
        requirements=frozenset({"numeric_series"}),
        # The current chart is screen-reader labelled, but animates without consulting
        # reduced-motion. Do not claim that capability until the renderer guarantees it.
        accessibility=frozenset(
            {
                AccessibilityCapability.KEYBOARD,
                AccessibilityCapability.SCREEN_READER,
                AccessibilityCapability.NO_DRAG_ALTERNATIVE,
            }
        ),
        rank=20,
    ),
    "QuizItem": _descriptor(
        "QuizItem",
        missions=frozenset(
            {CognitiveMission.RECOGNIZE, CognitiveMission.DECIDE, CognitiveMission.EXPLAIN}
        ),
        source_functions=frozenset({SourceFunction.ASSESS}),
        presentations=frozenset({Presentation.TEXT}),
        producer_kind=ProducerKind.ASSESSMENT,
        affordances=frozenset({"submit_answer", "receive_feedback"}),
        evidence_events=frozenset({"answer_submitted"}),
        state_model_ref="skillnet-quiz-item/1",
        accessibility=_INTERACTIVE_ACCESSIBILITY,
        rank=10,
    ),
    "BeforeAfter": _descriptor(
        "BeforeAfter",
        missions=frozenset({CognitiveMission.RECOGNIZE, CognitiveMission.INTERPRET}),
        source_functions=frozenset({SourceFunction.CONTRAST}),
        presentations=frozenset({Presentation.TEXT}),
        producer_kind=ProducerKind.CONTENT,
        affordances=frozenset({"compare_two_states"}),
        rank=10,
    ),
    "Markdown": LegacyComponentPolicy(
        exclusion_reason="non-LLM fallback representation outside on-the-fly planning"
    ),
    "DragOrder": _descriptor(
        "DragOrder",
        missions=frozenset({CognitiveMission.RECONSTRUCT, CognitiveMission.DECIDE}),
        source_functions=frozenset({SourceFunction.PROCEDURE, SourceFunction.ASSESS}),
        presentations=frozenset({Presentation.TEXT}),
        producer_kind=ProducerKind.ASSESSMENT,
        affordances=frozenset({"reorder_items", "receive_feedback"}),
        evidence_events=frozenset({"order_checked"}),
        state_model_ref="skillnet-drag-order/1",
        # Keyboard dragging exists; a non-drag pointer alternative does not.
        accessibility=_INTERACTIVE_ACCESSIBILITY,
        rank=20,
    ),
    "AudioExplanation": _descriptor(
        "AudioExplanation",
        missions=frozenset({CognitiveMission.RECOGNIZE, CognitiveMission.EXPLAIN}),
        source_functions=frozenset(
            {
                SourceFunction.ENUMERATE,
                SourceFunction.PROCEDURE,
                SourceFunction.QUANTIFY,
                SourceFunction.CONTRAST,
                SourceFunction.VARY,
                SourceFunction.EXPLORE,
                SourceFunction.LOCATE,
            }
        ),
        presentations=frozenset({Presentation.AUDIO}),
        producer_kind=ProducerKind.MEDIA,
        affordances=frozenset({"listen", "follow_highlighted_text"}),
        requirements=frozenset({"tts_service"}),
        accessibility=_INTERACTIVE_ACCESSIBILITY,
        rank=30,
    ),
    "PronunciationExercise": _descriptor(
        "PronunciationExercise",
        missions=frozenset({CognitiveMission.PRODUCE}),
        source_functions=frozenset({SourceFunction.EXPLORE, SourceFunction.ASSESS}),
        presentations=frozenset({Presentation.AUDIO}),
        producer_kind=ProducerKind.MEDIA,
        affordances=frozenset({"listen", "record_voice", "compare_waveforms"}),
        evidence_events=frozenset({"voice_recorded"}),
        state_model_ref="skillnet-pronunciation/1",
        requirements=frozenset({"tts_service", "microphone"}),
        accessibility=_INTERACTIVE_ACCESSIBILITY,
        rank=20,
    ),
    "Flashcard": _descriptor(
        "Flashcard",
        missions=frozenset({CognitiveMission.RECOGNIZE, CognitiveMission.RECONSTRUCT}),
        source_functions=frozenset({SourceFunction.ENUMERATE, SourceFunction.EXPLORE}),
        presentations=frozenset({Presentation.TEXT}),
        producer_kind=ProducerKind.CONTENT,
        affordances=frozenset({"attempt_recall", "reveal_answer", "rate_recall"}),
        evidence_events=frozenset({"answer_revealed", "recall_rated"}),
        state_model_ref="didact.flashcard/1",
        accessibility=_INTERACTIVE_ACCESSIBILITY,
        rank=15,
    ),
    "HintReveal": _descriptor(
        "HintReveal",
        missions=frozenset({CognitiveMission.EXPLAIN, CognitiveMission.RECONSTRUCT, CognitiveMission.DECIDE}),
        source_functions=frozenset({SourceFunction.EXPLORE, SourceFunction.PROCEDURE, SourceFunction.ASSESS}),
        presentations=frozenset({Presentation.TEXT}),
        producer_kind=ProducerKind.CONTENT,
        affordances=frozenset({"request_progressive_hint", "reveal_solution"}),
        evidence_events=frozenset({"hint_viewed", "solution_revealed"}),
        state_model_ref="didact.hint-reveal/1",
        accessibility=_INTERACTIVE_ACCESSIBILITY,
        rank=25,
    ),
    "DidactGlossary": _descriptor(
        "DidactGlossary",
        missions=frozenset({CognitiveMission.RECOGNIZE, CognitiveMission.RECONSTRUCT}),
        source_functions=frozenset({SourceFunction.ENUMERATE, SourceFunction.EXPLORE}),
        presentations=frozenset({Presentation.TEXT}),
        producer_kind=ProducerKind.CONTENT,
        affordances=frozenset({"inspect_term", "reveal_definition"}),
        accessibility=_INTERACTIVE_ACCESSIBILITY,
        rank=35,
    ),
    "DidactTimeline": _descriptor(
        "DidactTimeline",
        missions=frozenset({CognitiveMission.RECOGNIZE, CognitiveMission.INTERPRET}),
        source_functions=frozenset({SourceFunction.PROCEDURE, SourceFunction.EXPLORE}),
        presentations=frozenset({Presentation.TEXT}),
        producer_kind=ProducerKind.CONTENT,
        affordances=frozenset({"inspect_sequence"}),
        rank=20,
    ),
    "DidactWorkedExample": _descriptor(
        "DidactWorkedExample",
        missions=frozenset({CognitiveMission.INTERPRET, CognitiveMission.EXPLAIN}),
        source_functions=frozenset({SourceFunction.PROCEDURE, SourceFunction.EXPLORE}),
        presentations=frozenset({Presentation.TEXT}),
        producer_kind=ProducerKind.CONTENT,
        affordances=frozenset({"reveal_solution_steps", "inspect_transfer_cue"}),
        accessibility=_INTERACTIVE_ACCESSIBILITY,
        rank=25,
    ),
    # Generic renderer shell. The neutral Didact descriptor selected upstream remains
    # the pedagogical source of truth; this policy only states what the OpenUI host can
    # do with the already-materialised activity id.
    "DidactActivity": _descriptor(
        "DidactActivity",
        missions=frozenset(
            {
                CognitiveMission.INTERPRET,
                CognitiveMission.RECONSTRUCT,
                CognitiveMission.DECIDE,
                CognitiveMission.EXPLAIN,
            }
        ),
        source_functions=frozenset({SourceFunction.EXPLORE, SourceFunction.ASSESS}),
        presentations=frozenset({Presentation.SIMULATION}),
        producer_kind=ProducerKind.SIMULATION,
        affordances=frozenset({"perform_activity", "submit_evidence"}),
        evidence_events=frozenset({"activity_started", "activity_submitted"}),
        state_model_ref="activity-definition/1",
        accessibility=_INTERACTIVE_ACCESSIBILITY,
        rank=40,
    ),
}


def adapt_legacy_openui_catalog(kit: UIKit = UI_KIT) -> tuple[ComponentDescriptor, ...]:
    """Return deterministic planning descriptors for eligible legacy components.

    A different component library should provide a different adapter to the same
    ``ComponentDescriptor`` contract. This function deliberately has no side effects and
    does not modify the live kit or make components available to production agents.
    """
    names = kit.names
    if len(names) != len(set(names)):
        raise LegacyOpenUICatalogDrift("OpenUI catalogue contains duplicate component names")

    actual = set(names)
    declared = set(LEGACY_OPENUI_POLICIES)
    if actual != declared:
        missing = sorted(actual - declared)
        stale = sorted(declared - actual)
        raise LegacyOpenUICatalogDrift(
            f"OpenUI policy drift: missing={missing!r}, stale={stale!r}"
        )

    return tuple(
        policy.descriptor
        for name in names
        if (policy := LEGACY_OPENUI_POLICIES[name]).descriptor is not None
    )


__all__ = [
    "LEGACY_OPENUI_POLICIES",
    "LegacyComponentPolicy",
    "LegacyOpenUICatalogDrift",
    "adapt_legacy_openui_catalog",
]
