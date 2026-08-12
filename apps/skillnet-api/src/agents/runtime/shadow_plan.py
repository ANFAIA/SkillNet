"""Fail-open observation of the experimental personalization planner.

The live OpenUI pipeline remains authoritative. This module only projects inputs the
runtime already computed into the pure planner and returns a JSON-safe trace for graph
state and structured logs. It performs no I/O and never calls an LLM.
"""

from __future__ import annotations

import enum
from dataclasses import asdict
from typing import Any

from src.core.logging import get_logger
from src.personalization.legacy_openui_catalog import adapt_legacy_openui_catalog
from src.personalization.plan import (
    CognitiveMission,
    Declined,
    LearningObjective,
    SourceFunction,
    plan_experience,
)
from src.personalization.projection import project_runtime_signals
from src.render.kit import ContentFunction

logger = get_logger(__name__)

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


def build_shadow_plan_trace(state: dict[str, Any]) -> dict[str, Any]:
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
        functions = frozenset(ordered_functions)
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
        )
        outcome = plan_experience(
            objective, projection, adapt_legacy_openui_catalog()
        )
        trace = {
            "trace_version": "plan-trace/1",
            "mode": "shadow",
            "status": "declined" if isinstance(outcome, Declined) else "planned",
            "mission_rationale": mission_rationale,
            "live": live,
            "projection": _json_safe(asdict(projection)),
            "shadow": _json_safe(asdict(outcome)),
        }
        logger.info("personalization_plan_trace %s", trace)
        return trace
    except Exception as exc:  # noqa: BLE001 - observation must never break a render
        trace = {
            "trace_version": "plan-trace/1",
            "mode": "shadow",
            "status": "error",
            "live": live,
            "error_code": type(exc).__name__,
        }
        logger.warning("personalization_plan_trace %s", trace, exc_info=True)
        return trace


__all__ = ["build_shadow_plan_trace"]
