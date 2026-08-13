"""Fail-open observation of the experimental personalization planner.

The live OpenUI pipeline remains authoritative. This module only projects inputs the
runtime already computed into the pure planner and returns a JSON-safe trace for graph
state and structured logs. It performs no I/O and never calls an LLM.
"""

from __future__ import annotations

import enum
from dataclasses import asdict, replace
from typing import Any

from src.core.logging import get_logger
from src.personalization.didact_descriptors import (
    DidactExposureError,
    export_didact_descriptors,
    openui_names_for_shortlist,
)
from src.personalization.legacy_openui_catalog import adapt_legacy_openui_catalog
from src.personalization.plan import (
    CognitiveMission,
    Declined,
    LearningObjective,
    SourceFunction,
    plan_experience,
)
from src.personalization.projection import (
    longitudinal_projection_from_mapping,
    project_runtime_signals,
)
from src.personalization.selection_policy import (
    ProgressiveStage,
    SelectionCandidate,
    SelectionExecution,
    SelectionPolicyError,
    SelectionRequest,
    SelectionStrategy,
    runtime_execution,
    select,
)
from src.render.kit import ContentFunction
from src.render.prompt_slice import RUNTIME_SCOPE_POLICY_VERSION

logger = get_logger(__name__)

SHORTLIST_MIN = 3
SHORTLIST_MAX = 5

_SOURCE_FUNCTIONS = {
    ContentFunction.ENUMERAR.value: SourceFunction.ENUMERATE,
    ContentFunction.PROCEDIMENTAR.value: SourceFunction.PROCEDURE,
    ContentFunction.CUANTIFICAR.value: SourceFunction.QUANTIFY,
    ContentFunction.CONTRASTAR.value: SourceFunction.CONTRAST,
    ContentFunction.VARIAR.value: SourceFunction.VARY,
    ContentFunction.EXPLORAR.value: SourceFunction.EXPLORE,
    ContentFunction.LOCALIZAR.value: SourceFunction.LOCATE,
    ContentFunction.EVALUAR.value: SourceFunction.ASSESS,
}

_MISSION_FOR_SOURCE = {
    SourceFunction.PROCEDURE: CognitiveMission.RECONSTRUCT,
    SourceFunction.QUANTIFY: CognitiveMission.INTERPRET,
    SourceFunction.EXPLORE: CognitiveMission.INTERPRET,
    SourceFunction.VARY: CognitiveMission.DECIDE,
    SourceFunction.CONTRAST: CognitiveMission.RECOGNIZE,
    SourceFunction.ENUMERATE: CognitiveMission.RECOGNIZE,
    SourceFunction.LOCATE: CognitiveMission.RECOGNIZE,
    SourceFunction.ASSESS: CognitiveMission.DECIDE,
}

def _source_functions(
    state: dict[str, Any],
) -> tuple[tuple[SourceFunction, ...], str]:
    """Keep detector specificity order; never derive a mission from set ordering."""
    values = tuple(
        dict.fromkeys(
            _SOURCE_FUNCTIONS[value]
            for value in state.get("shape_functions") or ()
            if value in _SOURCE_FUNCTIONS
        )
    )
    if values:
        return values, "MISSION_FROM_FIRST_SHAPE_FUNCTION"
    fallback = {
        "chart": SourceFunction.QUANTIFY,
        "simulation": SourceFunction.EXPLORE,
        "exercise": SourceFunction.ASSESS,
    }.get(str(state.get("ui_format") or ""), SourceFunction.ENUMERATE)
    return (fallback,), "MISSION_FROM_UI_FORMAT_FALLBACK"


def _json_safe(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    return value


def _renderer_safe_shortlist(outcome: Any) -> tuple[str, ...]:
    """Project planned ids through the actual emission boundary, preserving rank."""
    if isinstance(outcome, Declined):
        return ()
    available_openui = {
        descriptor.component_id for descriptor in adapt_legacy_openui_catalog()
    }
    selected: list[str] = []
    for candidate in outcome.component_candidates:
        component_id = candidate.component_id
        if component_id in available_openui:
            names = (component_id,)
        elif component_id.startswith("didact."):
            try:
                # This is the hard renderer + emission + host-port gate. A blocked
                # Didact component is skipped, never silently exposed to the model.
                names = openui_names_for_shortlist((component_id,))
            except DidactExposureError:
                continue
        else:
            continue
        for name in names:
            if name not in selected:
                selected.append(name)
        if len(selected) >= SHORTLIST_MAX:
            break
    return tuple(selected[:SHORTLIST_MAX])


def _apply_selection(
    outcome: Any,
    *,
    strategy: SelectionStrategy | str,
    execution: SelectionExecution | str,
    progressive_stage: ProgressiveStage | str,
) -> tuple[Any, dict[str, Any]]:
    requested_strategy = SelectionStrategy.parse(strategy)
    requested_execution = SelectionExecution.parse(execution)
    effective_execution = runtime_execution(requested_execution, requested_strategy)
    trace: dict[str, Any] = {
        "requested_strategy": requested_strategy.value,
        "requested_execution": requested_execution.value,
        "effective_execution": effective_execution.value,
        "executed_strategy": None,
        "status": "off" if effective_execution is SelectionExecution.OFF else "pending",
    }
    if isinstance(outcome, Declined) or effective_execution is SelectionExecution.OFF:
        if isinstance(outcome, Declined):
            trace["status"] = "not_applicable"
        return outcome, trace

    try:
        result = select(
            SelectionRequest(
                strategy=requested_strategy,
                candidates=tuple(
                    SelectionCandidate(
                        candidate_id=item.component_id,
                        portfolio=item.producer_kind.value,
                    )
                    for item in outcome.component_candidates
                ),
                progressive_stage=ProgressiveStage(progressive_stage),
            )
        )
    except (SelectionPolicyError, ValueError) as exc:
        trace.update(
            {
                "status": "rejected",
                "error_code": type(exc).__name__,
                "reason": str(exc),
            }
        )
        return outcome, trace

    trace.update(
        {
            "status": (
                "executed"
                if effective_execution is SelectionExecution.LIVE
                else "shadowed"
            ),
            "executed_strategy": (
                result.trace.executed_strategy.value
                if effective_execution is SelectionExecution.LIVE
                else None
            ),
            "shadow_strategy": (
                result.trace.executed_strategy.value
                if effective_execution is SelectionExecution.SHADOW
                else None
            ),
            "policy_trace": _json_safe(asdict(result.trace)),
        }
    )
    if effective_execution is not SelectionExecution.LIVE:
        return outcome, trace

    by_id = {item.component_id: item for item in outcome.component_candidates}
    selected = tuple(by_id[candidate_id] for candidate_id in result.selected_ids)
    return replace(outcome, component_candidates=selected), trace


def build_shadow_plan_trace(
    state: dict[str, Any],
    *,
    mode: str = "shadow",
    selection_strategy: SelectionStrategy | str = SelectionStrategy.TOP5,
    selection_execution: SelectionExecution | str = SelectionExecution.SHADOW,
) -> dict[str, Any]:
    """Return a PlanTrace; planner failures become data and never block rendering."""
    node = state.get("node") or {}
    profile = state.get("profile") or {}
    node_state = state.get("node_state") or {}
    live = {
        "ui_format": state.get("ui_format"),
        "shape_functions": list(state.get("shape_functions") or ()),
        "shape_summary": state.get("shape_summary"),
        "assessment_block": state.get("assessment_block"),
        "assessment_item_type": state.get("assessment_item_type"),
    }
    try:
        ordered_functions, mission_rationale = _source_functions(state)
        # The detected source shape remains primary, while EXPLORE expresses that any
        # source-backed node may be turned into an inspectable/practice experience. This
        # prevents a narrow textual detector from reducing a rich component inventory to
        # one literal representation.
        functions = frozenset((*ordered_functions, SourceFunction.EXPLORE))
        mission = _MISSION_FOR_SOURCE[ordered_functions[0]]
        requirements = frozenset(
            {"numeric_series"} if SourceFunction.QUANTIFY in functions else set()
        )
        objective = LearningObjective(
            objective_id=str(state.get("node_id") or node.get("id") or "unknown"),
            objective_version=max(1, int(state.get("schema_version") or 1)),
            mission=mission,
            source_functions=functions,
            available_requirements=requirements,
        )
        longitudinal = longitudinal_projection_from_mapping(
            profile.get("longitudinal_history")
            if isinstance(profile.get("longitudinal_history"), dict)
            else None
        )
        projection = project_runtime_signals(
            role_title=profile.get("role_title"),
            sector=profile.get("sector"),
            experience_level=profile.get("experience_level"),
            scaffold_band=state.get("scaffold_band"),
            preset=profile.get("preset"),
            format_vector=profile.get("format_vector"),
            learning_preferences=profile.get("learning_preferences"),
            accessibility=state.get("accessibility"),
            nodes_completed=int(profile.get("nodes_completed") or 0),
            last_error_kind=node_state.get("last_error_kind"),
            base_density=int(state.get("effective_density") or 2),
            longitudinal_history=longitudinal,
        )
        # Retrieval/planning sees the complete installed Didact inventory. Prompt
        # exposure is a later, stricter operation in `_renderer_safe_shortlist`.
        catalog = (*adapt_legacy_openui_catalog(), *export_didact_descriptors())
        outcome = plan_experience(objective, projection, catalog)
        selected_outcome, selection_trace = _apply_selection(
            outcome,
            strategy=selection_strategy,
            execution=selection_execution,
            progressive_stage=state.get("selection_progressive_stage")
            or ProgressiveStage.TOP3,
        )
        shortlist = _renderer_safe_shortlist(selected_outcome)
        planned = state.get("assessment_item_type")
        if isinstance(planned, str) and planned.startswith("didact."):
            try:
                planned_names = openui_names_for_shortlist((planned,))
            except DidactExposureError:
                planned_names = ()
            merged: list[str] = []
            for name in (*planned_names, *shortlist):
                if name not in merged:
                    merged.append(name)
            shortlist = tuple(merged[:SHORTLIST_MAX])
        trace = {
            "trace_version": "plan-trace/2",
            "mode": mode,
            "status": "declined" if isinstance(outcome, Declined) else "planned",
            "mission_rationale": mission_rationale,
            "live": live,
            "projection": _json_safe(asdict(projection)),
            "longitudinal_history": _json_safe(asdict(longitudinal)),
            "longitudinal_decision_digest": longitudinal.decision_digest,
            "shadow": _json_safe(asdict(outcome)),
            "selection": selection_trace,
            "inventory_size": len(catalog),
            "prompt_component_ids": list(shortlist),
            "shortlist_policy": RUNTIME_SCOPE_POLICY_VERSION,
        }
        logger.info("personalization_plan_trace %s", trace)
        return trace
    except Exception as exc:
        trace = {
            "trace_version": "plan-trace/2",
            "mode": mode,
            "status": "error",
            "live": live,
            "error_code": type(exc).__name__,
        }
        logger.warning("personalization_plan_trace %s", trace, exc_info=True)
        return trace


__all__ = ["build_shadow_plan_trace"]
