"""Executable authoring contracts for the Didact shells exposed by SkillNet.

The Didact manifests describe authoring intent, while the React exports define the
actual serializable props.  This module is the small host adapter between both: a
draft must satisfy these checks *before* an ActivityDefinition can be persisted.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Any


class ActivityDefinitionShapeError(ValueError):
    """A draft cannot mount as the selected Didact component."""


Validator = Callable[[Mapping[str, Any]], None]


def _record(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ActivityDefinitionShapeError(f"{path} must be an object")
    return value


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ActivityDefinitionShapeError(f"{path} must be non-empty text")
    return value


def _list(value: Any, path: str, *, minimum: int = 1) -> list[Any]:
    if not isinstance(value, list) or len(value) < minimum:
        raise ActivityDefinitionShapeError(f"{path} must contain at least {minimum} item(s)")
    return value


def _number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ActivityDefinitionShapeError(f"{path} must be a finite number")
    return float(value)


def _ids(items: list[Any], path: str) -> set[str]:
    values: list[str] = []
    for index, item in enumerate(items):
        values.append(_text(_record(item, f"{path}[{index}]").get("id"), f"{path}[{index}].id"))
    if len(values) != len(set(values)):
        raise ActivityDefinitionShapeError(f"{path} ids must be unique")
    return set(values)


def _definition(public: Mapping[str, Any], component_id: str) -> Mapping[str, Any]:
    return _record(public.get("definition"), f"{component_id}.definition")


def _validate_rubric(public: Mapping[str, Any]) -> None:
    criteria = _list(public.get("criteria"), "didact.rubric.criteria")
    _ids(criteria, "didact.rubric.criteria")
    for index, raw in enumerate(criteria):
        criterion = _record(raw, f"didact.rubric.criteria[{index}]")
        _text(criterion.get("label"), f"didact.rubric.criteria[{index}].label")
        levels = _list(criterion.get("levels"), f"didact.rubric.criteria[{index}].levels", minimum=2)
        _ids(levels, f"didact.rubric.criteria[{index}].levels")
        for level_index, raw_level in enumerate(levels):
            level = _record(raw_level, "level")
            _text(level.get("label"), f"criteria[{index}].levels[{level_index}].label")


def _validate_self_explanation(public: Mapping[str, Any]) -> None:
    _text(public.get("prompt"), "didact.self-explanation-prompt.prompt")
    scaffolds = public.get("scaffolds", [])
    if not isinstance(scaffolds, list) or not all(isinstance(value, str) and value.strip() for value in scaffolds):
        raise ActivityDefinitionShapeError("didact.self-explanation-prompt.scaffolds must be text items")


def _domain(value: Any, path: str) -> None:
    domain = _record(value, path)
    scale = domain.get("scale")
    if scale == "linear":
        low, high = _number(domain.get("min"), f"{path}.min"), _number(domain.get("max"), f"{path}.max")
        if high <= low:
            raise ActivityDefinitionShapeError(f"{path}.max must be greater than min")
    elif scale == "time":
        _text(domain.get("min"), f"{path}.min")
        _text(domain.get("max"), f"{path}.max")
    else:
        raise ActivityDefinitionShapeError(f"{path}.scale must be linear or time")


def _validate_data_explorer(public: Mapping[str, Any]) -> None:
    definition = _definition(public, "didact.data-explorer")
    if definition.get("schemaVersion") != "1.0.0":
        raise ActivityDefinitionShapeError("didact.data-explorer.definition.schemaVersion must be 1.0.0")
    _text(definition.get("id"), "didact.data-explorer.definition.id")
    _text(definition.get("title"), "didact.data-explorer.definition.title")
    axes = _record(definition.get("axes"), "didact.data-explorer.definition.axes")
    for axis_name in ("x", "y"):
        axis = _record(axes.get(axis_name), f"axes.{axis_name}")
        _text(axis.get("label"), f"axes.{axis_name}.label")
        _domain(axis.get("domain"), f"axes.{axis_name}.domain")
    series = _list(definition.get("series"), "didact.data-explorer.definition.series")
    series_ids = _ids(series, "didact.data-explorer.definition.series")
    for index, raw in enumerate(series):
        item = _record(raw, f"series[{index}]")
        _text(item.get("label"), f"series[{index}].label")
        if item.get("kind") not in {"line", "scatter"}:
            raise ActivityDefinitionShapeError(f"series[{index}].kind must be line or scatter")
        source = _record(item.get("source"), f"series[{index}].source")
        # Function expressions need a secured host evaluator, which this shell does not expose.
        if source.get("kind") != "points":
            raise ActivityDefinitionShapeError(f"series[{index}].source must contain grounded points")
        points = _list(source.get("points"), f"series[{index}].source.points")
        _ids(points, f"series[{index}].source.points")
        for point_index, raw_point in enumerate(points):
            point = _record(raw_point, "point")
            if not isinstance(point.get("x"), (str, int, float)) or not isinstance(point.get("y"), (str, int, float)):
                raise ActivityDefinitionShapeError(f"series[{index}].points[{point_index}] needs x and y values")
    table = _record(definition.get("table"), "didact.data-explorer.definition.table")
    if table.get("source") != "series":
        raise ActivityDefinitionShapeError("didact.data-explorer.definition.table.source must be series")
    _text(table.get("caption"), "didact.data-explorer.definition.table.caption")
    included = table.get("includeSeriesIds", [])
    if not isinstance(included, list) or not set(included).issubset(series_ids):
        raise ActivityDefinitionShapeError("table.includeSeriesIds must reference declared series")


def _validate_concept_map(public: Mapping[str, Any]) -> None:
    definition = _definition(public, "didact.concept-map")
    _text(definition.get("id"), "concept-map.definition.id")
    _text(definition.get("title"), "concept-map.definition.title")
    nodes = _list(definition.get("nodes"), "concept-map.definition.nodes", minimum=2)
    node_ids = _ids(nodes, "concept-map.definition.nodes")
    for item in nodes:
        _text(_record(item, "node").get("label"), "concept-map.node.label")
    relations = definition.get("initialRelations", [])
    if not isinstance(relations, list):
        raise ActivityDefinitionShapeError("concept-map.definition.initialRelations must be a list")
    _ids(relations, "concept-map.definition.initialRelations") if relations else None
    for raw in relations:
        relation = _record(raw, "relation")
        if relation.get("from") not in node_ids or relation.get("to") not in node_ids:
            raise ActivityDefinitionShapeError("concept-map relations must reference declared nodes")


def _validate_drawing(public: Mapping[str, Any]) -> None:
    definition = _definition(public, "didact.drawing-response")
    _text(definition.get("id"), "drawing-response.definition.id")
    _text(definition.get("title"), "drawing-response.definition.title")
    _text(definition.get("instructions"), "drawing-response.definition.instructions")
    tools = _list(definition.get("tools"), "drawing-response.definition.tools")
    if not set(tools).issubset({"freehand", "line", "marker"}):
        raise ActivityDefinitionShapeError("drawing-response tools are invalid")
    if definition.get("background") is not None:
        raise ActivityDefinitionShapeError("drawing-response background requires an asset-resolver port")


def _validate_equation(public: Mapping[str, Any]) -> None:
    definition = _definition(public, "didact.equation-workbench")
    for key in ("id", "title", "instructions", "initialExpression"):
        _text(definition.get(key), f"equation-workbench.definition.{key}")


def _validate_evidence(public: Mapping[str, Any]) -> None:
    definition = _definition(public, "didact.evidence-annotation")
    _text(definition.get("id"), "evidence-annotation.definition.id")
    _text(definition.get("title"), "evidence-annotation.definition.title")
    for key in ("segments", "categories"):
        items = _list(definition.get(key), f"evidence-annotation.definition.{key}")
        _ids(items, f"evidence-annotation.definition.{key}")
        label_key = "text" if key == "segments" else "label"
        for item in items:
            _text(_record(item, key).get(label_key), f"evidence-annotation.{key}.{label_key}")


def _validate_measurement(public: Mapping[str, Any]) -> None:
    definition = _definition(public, "didact.measurement-lab")
    _text(definition.get("id"), "measurement-lab.definition.id")
    _text(definition.get("title"), "measurement-lab.definition.title")
    instrument = _record(definition.get("instrument"), "measurement-lab.definition.instrument")
    if instrument.get("kind") not in {"linear", "dial"}:
        raise ActivityDefinitionShapeError("measurement-lab instrument.kind must be linear or dial")
    low = _number(instrument.get("min"), "instrument.min")
    high = _number(instrument.get("max"), "instrument.max")
    step = _number(instrument.get("step"), "instrument.step")
    _text(instrument.get("unit"), "instrument.unit")
    if high <= low or step <= 0:
        raise ActivityDefinitionShapeError("measurement-lab needs max > min and step > 0")
    observed = definition.get("observedReading")
    if observed is not None and not low <= _number(observed, "observedReading") <= high:
        raise ActivityDefinitionShapeError("observedReading must be inside the instrument range")


AUTHORING_VALIDATORS: Mapping[str, Validator] = {
    "didact.rubric": _validate_rubric,
    "didact.data-explorer": _validate_data_explorer,
    "didact.self-explanation-prompt": _validate_self_explanation,
    "didact.concept-map": _validate_concept_map,
    "didact.drawing-response": _validate_drawing,
    "didact.equation-workbench": _validate_equation,
    "didact.evidence-annotation": _validate_evidence,
    "didact.measurement-lab": _validate_measurement,
}


def validate_component_definition(component_id: str, public: Mapping[str, Any]) -> None:
    """Reject unknown shells and definitions that cannot mount honestly."""

    validator = AUTHORING_VALIDATORS.get(component_id)
    if validator is None:
        raise ActivityDefinitionShapeError(f"no authoring validator for {component_id}")
    validator(public)


__all__ = ["AUTHORING_VALIDATORS", "ActivityDefinitionShapeError", "validate_component_definition"]
