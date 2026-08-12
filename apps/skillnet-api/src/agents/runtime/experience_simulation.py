"""Measurement adapter for shadow learning-experience plans.

Selection belongs exclusively to :mod:`src.personalization.plan`.  This module only
turns its plan (or explicit decline) into an inspectable simulated screen and measures
the experiential affordances declared by a fixture catalogue.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from src.agents.runtime.screen_eval import CriticalFact, ScreenScenario, evaluate_screen
from src.personalization.plan import (
    ComponentDescriptor,
    Declined,
    LearningExperiencePlan,
    LearningObjective,
    PersonalizationProjection,
    plan_experience,
)


@dataclass(frozen=True)
class SimulationResult:
    profile_id: str
    catalogue_id: str
    objective_id: str
    selected_component: str | None
    producer_kind: str | None
    evidence_events: tuple[str, ...]
    state_model_ref: str | None
    declined: bool
    decline_reasons: tuple[Mapping[str, Any], ...]
    preference_satisfied: bool
    experiential_affordance_coverage: float
    matched_affordances: tuple[str, ...]
    rationale_codes: tuple[str, ...]
    screen_metrics: Mapping[str, Any] | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def simulate_experience(
    *,
    objective: LearningObjective,
    projection: PersonalizationProjection,
    profile_id: str,
    catalogue_id: str,
    catalogue: tuple[ComponentDescriptor, ...],
    desired_affordances: frozenset[str],
    evidence_text: str,
    critical_facts: tuple[CriticalFact, ...] = (),
) -> SimulationResult:
    """Plan once with the canonical resolver, then measure the resulting experience."""

    outcome = plan_experience(objective, projection, catalogue)
    if isinstance(outcome, Declined):
        reasons = tuple(
            {"reason": decline.reason.value, "component_ids": decline.component_ids}
            for decline in outcome.reasons
        )
        return SimulationResult(
            profile_id=profile_id,
            catalogue_id=catalogue_id,
            objective_id=objective.objective_id,
            selected_component=None,
            producer_kind=None,
            evidence_events=(),
            state_model_ref=None,
            declined=True,
            decline_reasons=reasons,
            preference_satisfied=False,
            experiential_affordance_coverage=0.0,
            matched_affordances=(),
            rationale_codes=(),
            screen_metrics=None,
        )

    assert isinstance(outcome, LearningExperiencePlan)
    selected = outcome.component_candidates[0]
    matched = tuple(sorted(desired_affordances & selected.affordances))
    coverage = len(matched) / len(desired_affordances) if desired_affordances else 1.0
    preference_satisfied = selected.presentation in projection.declared_presentations

    blueprint = {
        "blocks": [
            {"id": "learning_action", "type": selected.component_id, "intent": "concepto"}
        ]
    }
    ui_spec = {
        "root": "root",
        "components": [
            {"id": "root", "type": "Stack", "children": ["learning_action"]},
            {
                "id": "learning_action",
                "type": selected.component_id,
                "props": {"evidence": evidence_text},
            },
        ],
    }
    metrics = evaluate_screen(
        ScreenScenario(
            id=f"{catalogue_id}:{profile_id}",
            objective=objective.objective_id,
            blueprint=blueprint,
            ui_spec=ui_spec,
            critical_facts=critical_facts,
        )
    )
    return SimulationResult(
        profile_id=profile_id,
        catalogue_id=catalogue_id,
        objective_id=objective.objective_id,
        selected_component=selected.component_id,
        producer_kind=selected.producer_kind.value,
        evidence_events=tuple(sorted(selected.evidence_events)),
        state_model_ref=selected.state_model_ref,
        declined=False,
        decline_reasons=(),
        preference_satisfied=preference_satisfied,
        experiential_affordance_coverage=coverage,
        matched_affordances=matched,
        rationale_codes=outcome.rationale_codes,
        screen_metrics=metrics.as_dict(),
    )
