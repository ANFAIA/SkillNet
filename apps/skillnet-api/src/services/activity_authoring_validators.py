"""Executable authoring contracts for the Didact shells exposed by SkillNet.

The Didact manifests describe authoring intent, while the React exports define the
actual serializable props.  This module is the small host adapter between both: a
draft must satisfy these checks *before* an ActivityDefinition can be persisted.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


EVALUATED_COMPONENT_MODES = MappingProxyType(
    {
        "didact.matching": "assignments",
        "didact.sort": "sequence",
        "didact.categorize": "assignments",
        "didact.quiz.single-choice": "exact",
        "didact.quiz.multi-select": "set",
        "didact.quiz.true-false": "exact",
        "didact.quiz.fill-in-the-blank": "normalized_any",
        "didact.quiz.short-answer": "normalized_any",
        "didact.completion-problem": "keyed_text",
        "didact.numeric-question": "numeric",
        "didact.word-bank": "assignments",
        "didact.hotspot": "regions",
        "didact.label-diagram": "assignments",
    }
)


class ActivityDefinitionShapeError(ValueError):
    """A draft cannot mount as the selected Didact component."""


Validator = Callable[[Mapping[str, Any]], None]


@dataclass(frozen=True, slots=True)
class AuthoringContract:
    """One executable validator and the prompt example it owns."""

    validator: Validator
    example: Mapping[str, Any]


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


def _choice_items(
    value: Any, path: str, *, label: str = "content", identifier: str = "id"
) -> set[str]:
    items = _list(value, path, minimum=2)
    values = [
        _text(_record(raw, f"{path}[{index}]").get(identifier), f"{path}[{index}].{identifier}")
        for index, raw in enumerate(items)
    ]
    if len(values) != len(set(values)):
        raise ActivityDefinitionShapeError(f"{path} identifiers must be unique")
    for index, raw in enumerate(items):
        _text(_record(raw, f"{path}[{index}]").get(label), f"{path}[{index}].{label}")
    return set(values)


def _validate_evaluated_family(public: Mapping[str, Any], component_id: str) -> None:
    """Validate the public half of server-evaluated, answer-free activities."""

    if component_id == "didact.matching":
        _text(public.get("title"), f"{component_id}.title")
        sources = _choice_items(public.get("sources"), f"{component_id}.sources")
        targets = _choice_items(public.get("targets"), f"{component_id}.targets")
        if len(sources) != len(targets):
            raise ActivityDefinitionShapeError("matching sources and targets must have equal length")
        return
    if component_id == "didact.sort":
        _text(public.get("title"), f"{component_id}.title")
        _choice_items(public.get("items"), f"{component_id}.items")
        return
    if component_id == "didact.categorize":
        _text(public.get("title"), f"{component_id}.title")
        _choice_items(public.get("items"), f"{component_id}.items")
        _choice_items(public.get("categories"), f"{component_id}.categories")
        return
    if component_id.startswith("didact.quiz."):
        _text(public.get("question"), f"{component_id}.question")
        if component_id in {"didact.quiz.single-choice", "didact.quiz.multi-select"}:
            _choice_items(
                public.get("options"),
                f"{component_id}.options",
                label="label",
                identifier="value",
            )
        return
    if component_id == "didact.completion-problem":
        _text(public.get("problem"), f"{component_id}.problem")
        steps = _list(public.get("steps"), f"{component_id}.steps", minimum=2)
        _ids(steps, f"{component_id}.steps")
        completion_count = 0
        for index, raw in enumerate(steps):
            step = _record(raw, f"{component_id}.steps[{index}]")
            if step.get("kind") not in {"worked", "completion"}:
                raise ActivityDefinitionShapeError(f"{component_id}.steps[{index}].kind is invalid")
            _text(step.get("content" if step.get("kind") == "worked" else "prompt"), f"{component_id}.steps[{index}]")
            completion_count += step.get("kind") == "completion"
        if completion_count == 0:
            raise ActivityDefinitionShapeError("completion-problem needs a completion step")
        return
    if component_id == "didact.numeric-question":
        _text(public.get("prompt"), f"{component_id}.prompt")
        unit = public.get("unit")
        if unit is not None:
            unit_record = _record(unit, f"{component_id}.unit")
            _text(unit_record.get("symbol"), f"{component_id}.unit.symbol")
            if unit_record.get("policy", "display") not in {"display", "required"}:
                raise ActivityDefinitionShapeError(f"{component_id}.unit.policy is invalid")
        return
    if component_id == "didact.word-bank":
        _text(public.get("title"), f"{component_id}.title")
        options = _choice_items(public.get("options"), f"{component_id}.options")
        gaps = _list(public.get("gaps"), f"{component_id}.gaps")
        _ids(gaps, f"{component_id}.gaps")
        for index, raw in enumerate(gaps):
            gap = _record(raw, f"{component_id}.gaps[{index}]")
            if not any(isinstance(gap.get(key), str) and gap[key].strip() for key in ("before", "after", "prompt")):
                raise ActivityDefinitionShapeError(f"{component_id}.gaps[{index}] needs visible text")
        if len(options) < 2:
            raise ActivityDefinitionShapeError("word-bank needs at least two options")
        return
    raise ActivityDefinitionShapeError(f"no evaluated-family validator for {component_id}")


def _evaluated_contract(component_id: str, example: Mapping[str, Any]) -> AuthoringContract:
    return AuthoringContract(
        lambda public: _validate_evaluated_family(public, component_id),
        example,
    )


def _definition(public: Mapping[str, Any], component_id: str) -> Mapping[str, Any]:
    return _record(public.get("definition"), f"{component_id}.definition")


def _validate_rubric(public: Mapping[str, Any]) -> None:
    criteria = _list(public.get("criteria"), "didact.rubric.criteria")
    _ids(criteria, "didact.rubric.criteria")
    for index, raw in enumerate(criteria):
        criterion = _record(raw, f"didact.rubric.criteria[{index}]")
        _text(criterion.get("label"), f"didact.rubric.criteria[{index}].label")
        levels = _list(
            criterion.get("levels"), f"didact.rubric.criteria[{index}].levels", minimum=2
        )
        _ids(levels, f"didact.rubric.criteria[{index}].levels")
        for level_index, raw_level in enumerate(levels):
            level = _record(raw_level, "level")
            _text(level.get("label"), f"criteria[{index}].levels[{level_index}].label")


def _validate_self_explanation(public: Mapping[str, Any]) -> None:
    _text(public.get("prompt"), "didact.self-explanation-prompt.prompt")
    scaffolds = public.get("scaffolds", [])
    if not isinstance(scaffolds, list) or not all(
        isinstance(value, str) and value.strip() for value in scaffolds
    ):
        raise ActivityDefinitionShapeError(
            "didact.self-explanation-prompt.scaffolds must be text items"
        )


def _domain(value: Any, path: str) -> None:
    domain = _record(value, path)
    scale = domain.get("scale")
    if scale == "linear":
        low, high = (
            _number(domain.get("min"), f"{path}.min"),
            _number(domain.get("max"), f"{path}.max"),
        )
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
        raise ActivityDefinitionShapeError(
            "didact.data-explorer.definition.schemaVersion must be 1.0.0"
        )
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
            raise ActivityDefinitionShapeError(
                f"series[{index}].source must contain grounded points"
            )
        points = _list(source.get("points"), f"series[{index}].source.points")
        _ids(points, f"series[{index}].source.points")
        for point_index, raw_point in enumerate(points):
            point = _record(raw_point, "point")
            if not isinstance(point.get("x"), (str, int, float)) or not isinstance(
                point.get("y"), (str, int, float)
            ):
                raise ActivityDefinitionShapeError(
                    f"series[{index}].points[{point_index}] needs x and y values"
                )
    table = _record(definition.get("table"), "didact.data-explorer.definition.table")
    if table.get("source") != "series":
        raise ActivityDefinitionShapeError(
            "didact.data-explorer.definition.table.source must be series"
        )
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
            raise ActivityDefinitionShapeError(
                "concept-map relations must reference declared nodes"
            )


def _validate_drawing(public: Mapping[str, Any]) -> None:
    definition = _definition(public, "didact.drawing-response")
    _text(definition.get("id"), "drawing-response.definition.id")
    _text(definition.get("title"), "drawing-response.definition.title")
    _text(definition.get("instructions"), "drawing-response.definition.instructions")
    tools = _list(definition.get("tools"), "drawing-response.definition.tools")
    if not set(tools).issubset({"freehand", "line", "marker"}):
        raise ActivityDefinitionShapeError("drawing-response tools are invalid")
    if definition.get("background") is not None:
        raise ActivityDefinitionShapeError(
            "drawing-response background requires an asset-resolver port"
        )


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


def _asset_ref(public: Mapping[str, Any], component_id: str) -> None:
    _text(public.get("assetRef"), f"{component_id}.assetRef")
    refs = _list(public.get("sourceRefs"), f"{component_id}.sourceRefs")
    for index, ref in enumerate(refs):
        _text(ref, f"{component_id}.sourceRefs[{index}]")


def _coordinate(value: Any, path: str) -> float:
    coordinate = _number(value, path)
    if not 0 <= coordinate <= 1:
        raise ActivityDefinitionShapeError(f"{path} must be between 0 and 1")
    return coordinate


def _validate_hotspot(public: Mapping[str, Any]) -> None:
    component_id = "didact.hotspot"
    _asset_ref(public, component_id)
    _text(public.get("title"), f"{component_id}.title")
    _text(public.get("alt"), f"{component_id}.alt")
    _text(public.get("longDescription"), f"{component_id}.longDescription")
    geometry = _record(public.get("geometry"), f"{component_id}.geometry")
    if geometry.get("verified") is not True:
        raise ActivityDefinitionShapeError("hotspot geometry must be independently verified")
    regions = _list(public.get("regions"), f"{component_id}.regions")
    _ids(regions, f"{component_id}.regions")
    for index, raw in enumerate(regions):
        region = _record(raw, f"regions[{index}]")
        _text(region.get("label"), f"regions[{index}].label")
        x = _coordinate(region.get("x"), f"regions[{index}].x")
        y = _coordinate(region.get("y"), f"regions[{index}].y")
        width = _coordinate(region.get("width"), f"regions[{index}].width")
        height = _coordinate(region.get("height"), f"regions[{index}].height")
        if width <= 0 or height <= 0 or x + width > 1 or y + height > 1:
            raise ActivityDefinitionShapeError("hotspot regions must be positive and inside the asset")


def _validate_label_diagram(public: Mapping[str, Any]) -> None:
    component_id = "didact.label-diagram"
    _asset_ref(public, component_id)
    _text(public.get("title"), f"{component_id}.title")
    _text(public.get("alt"), f"{component_id}.alt")
    _text(public.get("longDescription"), f"{component_id}.longDescription")
    geometry = _record(public.get("geometry"), f"{component_id}.geometry")
    if geometry.get("verified") is not True:
        raise ActivityDefinitionShapeError("label-diagram geometry must be independently verified")
    targets = _list(public.get("targets"), f"{component_id}.targets")
    target_ids = _ids(targets, f"{component_id}.targets")
    items = _list(public.get("items"), f"{component_id}.items")
    item_ids = _ids(items, f"{component_id}.items")
    if len(target_ids) != len(item_ids):
        raise ActivityDefinitionShapeError("label-diagram needs one label per target")
    for index, raw in enumerate(targets):
        target = _record(raw, f"targets[{index}]")
        _text(target.get("label"), f"targets[{index}].label")
        _coordinate(target.get("x"), f"targets[{index}].x")
        _coordinate(target.get("y"), f"targets[{index}].y")
    for index, raw in enumerate(items):
        _text(_record(raw, f"items[{index}]").get("content"), f"items[{index}].content")


def _validate_interactive_media(public: Mapping[str, Any]) -> None:
    component_id = "didact.interactive-media"
    _asset_ref(public, component_id)
    definition = _definition(public, component_id)
    if definition.get("schemaVersion") != "1.0.0":
        raise ActivityDefinitionShapeError("interactive-media schemaVersion must be 1.0.0")
    _text(definition.get("id"), "interactive-media.definition.id")
    _text(definition.get("title"), "interactive-media.definition.title")
    media = _record(definition.get("media"), "interactive-media.definition.media")
    if media.get("assetRef") != public.get("assetRef"):
        raise ActivityDefinitionShapeError("interactive-media must use the declared assetRef")
    if media.get("kind") not in {"audio", "video"}:
        raise ActivityDefinitionShapeError("interactive-media media.kind must be audio or video")
    duration = _number(media.get("durationMs"), "interactive-media.media.durationMs")
    if duration <= 0 or duration > 14_400_000:
        raise ActivityDefinitionShapeError("interactive-media duration must be at most four hours")
    checkpoints = _list(definition.get("checkpoints"), "interactive-media.checkpoints")
    if len(checkpoints) > 24:
        raise ActivityDefinitionShapeError("interactive-media supports at most 24 checkpoints")
    _ids(checkpoints, "interactive-media.checkpoints")
    previous = -1.0
    for index, raw in enumerate(checkpoints):
        checkpoint = _record(raw, f"checkpoints[{index}]")
        at_ms = _number(checkpoint.get("atMs"), f"checkpoints[{index}].atMs")
        if at_ms < previous or not 0 <= at_ms <= duration:
            raise ActivityDefinitionShapeError("interactive-media checkpoints must be ordered within duration")
        previous = at_ms
        activity = _record(checkpoint.get("activity"), f"checkpoints[{index}].activity")
        _text(activity.get("id"), f"checkpoints[{index}].activity.id")
        _text(activity.get("manifestId"), f"checkpoints[{index}].activity.manifestId")
        _record(activity.get("authoring"), f"checkpoints[{index}].activity.authoring")
    completion = _record(definition.get("completion"), "interactive-media.completion")
    if completion.get("kind") not in {"media-ended", "required-checkpoints", "both"}:
        raise ActivityDefinitionShapeError("interactive-media completion policy is invalid")


def _validate_progress_indicator(public: Mapping[str, Any]) -> None:
    """Labels only. Percent and status are injected from server-owned node state."""

    kind = public.get("kind", "lesson")
    if kind not in {"lesson", "skill"}:
        raise ActivityDefinitionShapeError("didact.progress.kind must be lesson or skill")
    _text(public.get("label"), "didact.progress.label")
    for forbidden in ("value", "percent", "status", "progress"):
        if forbidden in public:
            raise ActivityDefinitionShapeError(
                f"didact.progress.{forbidden} is host-owned and cannot be authored"
            )


def _validate_mastery_badge(public: Mapping[str, Any]) -> None:
    """Display copy only. Level and percent come from the ProgressPort."""

    _text(public.get("label"), "didact.mastery-badge.label")
    for forbidden in ("level", "percent", "value", "status"):
        if forbidden in public:
            raise ActivityDefinitionShapeError(
                f"didact.mastery-badge.{forbidden} is host-owned and cannot be authored"
            )


# Minimal mountable public definitions, colocated with the executable validators so the
# prompt contract cannot drift into a second hand-written authority. Values are examples,
# not defaults: the authoring model must replace their content with grounded source data.
AUTHORING_CONTRACTS: Mapping[str, AuthoringContract] = MappingProxyType(
    {
        "didact.matching": _evaluated_contract(
            "didact.matching",
            {
                "title": "Relaciona cada concepto",
                "sources": [{"id": "source-1", "content": "Concepto A"}, {"id": "source-2", "content": "Concepto B"}],
                "targets": [{"id": "target-1", "content": "Definición A"}, {"id": "target-2", "content": "Definición B"}],
                "evaluation": {"mode": "assignments", "expected": {"source-1": "target-1", "source-2": "target-2"}},
            },
        ),
        "didact.sort": _evaluated_contract(
            "didact.sort",
            {
                "title": "Ordena el procedimiento",
                "items": [{"id": "step-2", "content": "Segundo paso"}, {"id": "step-1", "content": "Primer paso"}],
                "evaluation": {"mode": "sequence", "expected": ["step-1", "step-2"]},
            },
        ),
        "didact.categorize": _evaluated_contract(
            "didact.categorize",
            {
                "title": "Clasifica los elementos",
                "items": [{"id": "item-1", "content": "Ejemplo A"}, {"id": "item-2", "content": "Ejemplo B"}],
                "categories": [{"id": "category-1", "content": "Grupo A"}, {"id": "category-2", "content": "Grupo B"}],
                "evaluation": {"mode": "assignments", "expected": {"item-1": "category-1", "item-2": "category-2"}},
            },
        ),
        "didact.quiz.single-choice": _evaluated_contract(
            "didact.quiz.single-choice",
            {
                "question": "Selecciona la respuesta correcta.",
                "options": [{"value": "a", "label": "Opción A"}, {"value": "b", "label": "Opción B"}],
                "evaluation": {"mode": "exact", "expected": "a"},
            },
        ),
        "didact.quiz.multi-select": _evaluated_contract(
            "didact.quiz.multi-select",
            {
                "question": "Selecciona todas las respuestas correctas.",
                "options": [{"value": "a", "label": "Opción A"}, {"value": "b", "label": "Opción B"}],
                "evaluation": {"mode": "set", "expected": ["a"]},
            },
        ),
        "didact.quiz.true-false": _evaluated_contract(
            "didact.quiz.true-false",
            {"question": "La afirmación documentada es verdadera.", "evaluation": {"mode": "exact", "expected": True}},
        ),
        # `normalized_any` accepts ANY member of `expected`, and the example is the only
        # place the model learns that. A one-element list taught it to emit a single
        # accepted string, which turns a typed answer into a lottery: the server already
        # forgives case, spacing and accents, but not "el ciclo" for "ciclo". So the
        # example ships several variants -- article in and out, singular and plural, a
        # synonym -- and the model copies that shape with the source's own wording.
        "didact.quiz.fill-in-the-blank": _evaluated_contract(
            "didact.quiz.fill-in-the-blank",
            {
                "question": "Completa la frase.",
                "evaluation": {
                    "mode": "normalized_any",
                    "expected": ["respuesta", "la respuesta", "respuestas"],
                },
            },
        ),
        "didact.quiz.short-answer": _evaluated_contract(
            "didact.quiz.short-answer",
            {
                "question": "Responde brevemente.",
                "evaluation": {
                    "mode": "normalized_any",
                    "expected": [
                        "respuesta fundamentada",
                        "la respuesta fundamentada",
                        "respuesta con fundamento",
                    ],
                },
            },
        ),
        "didact.completion-problem": _evaluated_contract(
            "didact.completion-problem",
            {
                "problem": "Completa los pasos que faltan.",
                "steps": [
                    {"id": "worked-1", "kind": "worked", "content": "Paso resuelto"},
                    {"id": "gap-1", "kind": "completion", "prompt": "Siguiente paso"},
                ],
                # Same reason as the quiz contracts above: `keyed_text` accepts any variant
                # listed for a gap, so the example lists more than one.
                "evaluation": {
                    "mode": "keyed_text",
                    "expected": {"gap-1": ["respuesta", "la respuesta"]},
                },
            },
        ),
        "didact.numeric-question": _evaluated_contract(
            "didact.numeric-question",
            {
                "prompt": "Introduce el valor documentado.",
                "unit": {"symbol": "kg", "policy": "display"},
                "evaluation": {"mode": "numeric", "value": 10, "absolute_tolerance": 0.1},
            },
        ),
        "didact.word-bank": _evaluated_contract(
            "didact.word-bank",
            {
                "title": "Completa las frases",
                "gaps": [
                    {"id": "gap-1", "before": "Antes", "after": "después"},
                    {"id": "gap-2", "prompt": "Segunda frase"},
                ],
                "options": [{"id": "option-1", "content": "término A"}, {"id": "option-2", "content": "término B"}],
                "evaluation": {"mode": "assignments", "expected": {"gap-1": "option-1", "gap-2": "option-2"}},
            },
        ),
        "didact.progress": AuthoringContract(
            _validate_progress_indicator,
            {"kind": "lesson", "label": "Progreso de esta lección"},
        ),
        "didact.mastery-badge": AuthoringContract(
            _validate_mastery_badge,
            {"label": "Dominio de esta lección"},
        ),
        "didact.rubric": AuthoringContract(
            _validate_rubric,
            {
                "criteria": [
                    {
                        "id": "criterion-1",
                        "label": "Criterio de la fuente",
                        "levels": [
                            {"id": "level-1", "label": "Necesita mejora"},
                            {"id": "level-2", "label": "Cumple"},
                        ],
                    }
                ],
            },
        ),
        "didact.self-explanation-prompt": AuthoringContract(
            _validate_self_explanation,
            {
                "prompt": "Explica la decisión usando una evidencia de la fuente.",
                "scaffolds": ["Nombra la regla aplicada."],
            },
        ),
        "didact.data-explorer": AuthoringContract(
            _validate_data_explorer,
            {
                "definition": {
                    "schemaVersion": "1.0.0",
                    "id": "grounded-data",
                    "title": "Datos de la fuente",
                    "axes": {
                        "x": {
                            "label": "Variable X",
                            "domain": {"scale": "linear", "min": 0, "max": 2},
                        },
                        "y": {
                            "label": "Variable Y",
                            "domain": {"scale": "linear", "min": 0, "max": 10},
                        },
                    },
                    "series": [
                        {
                            "id": "series-1",
                            "label": "Serie documentada",
                            "kind": "line",
                            "source": {
                                "kind": "points",
                                "points": [{"id": "point-1", "x": 1, "y": 4}],
                            },
                        }
                    ],
                    "table": {
                        "source": "series",
                        "caption": "Valores documentados",
                        "includeSeriesIds": ["series-1"],
                    },
                }
            },
        ),
        "didact.concept-map": AuthoringContract(
            _validate_concept_map,
            {
                "definition": {
                    "id": "concept-map",
                    "title": "Relaciones de la fuente",
                    "nodes": [
                        {"id": "concept-1", "label": "Concepto A"},
                        {"id": "concept-2", "label": "Concepto B"},
                    ],
                    "initialRelations": [
                        {
                            "id": "relation-1",
                            "from": "concept-1",
                            "to": "concept-2",
                            "label": "se relaciona con",
                        }
                    ],
                }
            },
        ),
        "didact.drawing-response": AuthoringContract(
            _validate_drawing,
            {
                "definition": {
                    "id": "drawing",
                    "title": "Representa el proceso",
                    "instructions": "Dibuja únicamente lo descrito por la fuente.",
                    "tools": ["line", "marker"],
                }
            },
        ),
        "didact.equation-workbench": AuthoringContract(
            _validate_equation,
            {
                "definition": {
                    "id": "equation",
                    "title": "Resuelve la expresión",
                    "instructions": "Transforma la expresión usando la regla documentada.",
                    "initialExpression": "2x=4",
                }
            },
        ),
        "didact.evidence-annotation": AuthoringContract(
            _validate_evidence,
            {
                "definition": {
                    "id": "evidence",
                    "title": "Identifica la evidencia",
                    "segments": [{"id": "segment-1", "text": "Fragmento literal de la fuente."}],
                    "categories": [{"id": "category-1", "label": "Regla"}],
                }
            },
        ),
        "didact.measurement-lab": AuthoringContract(
            _validate_measurement,
            {
                "definition": {
                    "id": "measurement",
                    "title": "Lee la medición",
                    "instrument": {
                        "kind": "linear",
                        "min": 0,
                        "max": 10,
                        "step": 1,
                        "unit": "unidad",
                    },
                    "observedReading": 4,
                }
            },
        ),
        "didact.hotspot": AuthoringContract(
            _validate_hotspot,
            {
                "assetRef": "COPY_AN_ALLOWED_OPAQUE_ASSET_REF",
                "sourceRefs": ["c1"],
                "title": "Localiza la zona documentada",
                "instructions": "Selecciona la región correcta.",
                "alt": "Diagrama accesible de la fuente",
                "longDescription": "Descripción completa del diagrama y sus regiones.",
                "geometry": {"verified": True, "method": "human-or-source-coordinates"},
                "regions": [{"id": "region-1", "label": "Región A", "x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2}],
                "evaluation": {"mode": "regions", "expected": ["region-1"]},
            },
        ),
        "didact.label-diagram": AuthoringContract(
            _validate_label_diagram,
            {
                "assetRef": "COPY_AN_ALLOWED_OPAQUE_ASSET_REF",
                "sourceRefs": ["c1"],
                "title": "Etiqueta el diagrama",
                "description": "Asigna cada etiqueta a su destino.",
                "alt": "Diagrama accesible de la fuente",
                "longDescription": "Descripción completa del diagrama y sus destinos.",
                "geometry": {"verified": True, "method": "human-or-source-coordinates"},
                "targets": [{"id": "target-1", "label": "Destino A", "x": 0.2, "y": 0.2}],
                "items": [{"id": "item-1", "content": "Etiqueta A", "accessibleLabel": "Etiqueta A"}],
                "evaluation": {"mode": "assignments", "expected": {"target-1": "item-1"}},
            },
        ),
        "didact.interactive-media": AuthoringContract(
            _validate_interactive_media,
            {
                "assetRef": "COPY_AN_ALLOWED_OPAQUE_ASSET_REF",
                "sourceRefs": ["c1"],
                "definition": {
                    "schemaVersion": "1.0.0",
                    "id": "grounded-media",
                    "title": "Medio interactivo",
                    "media": {"assetRef": "COPY_AN_ALLOWED_OPAQUE_ASSET_REF", "kind": "audio", "durationMs": 60000},
                    "checkpoints": [{"id": "checkpoint-1", "atMs": 30000, "activity": {"id": "reflection-1", "manifestId": "didact.self-explanation-prompt", "authoring": {"prompt": "Explica la idea principal."}}}],
                    "completion": {"kind": "both", "minimumWatchRatio": 0.8},
                },
            },
        ),
    }
)

# Compatibility projection for callers that need direct validator access. The component
# ids are authored only once, in AUTHORING_CONTRACTS.
AUTHORING_VALIDATORS: Mapping[str, Validator] = MappingProxyType(
    {component_id: contract.validator for component_id, contract in AUTHORING_CONTRACTS.items()}
)


def authoring_definition_contract(component_id: str) -> dict[str, Any]:
    """Return the validator-owned minimal definition for one supported shell."""
    contract = AUTHORING_CONTRACTS.get(component_id)
    if contract is None:
        raise ActivityDefinitionShapeError(f"no authoring contract for {component_id}")
    # Assert the example against the same executable authority every time it is exposed.
    contract.validator(contract.example)
    return deepcopy(dict(contract.example))


def validate_component_definition(component_id: str, public: Mapping[str, Any]) -> None:
    """Reject unknown shells and definitions that cannot mount honestly."""

    contract = AUTHORING_CONTRACTS.get(component_id)
    if contract is None:
        raise ActivityDefinitionShapeError(f"no authoring validator for {component_id}")
    contract.validator(public)


def validate_evaluation_definition(
    component_id: str,
    public: Mapping[str, Any],
    private: Mapping[str, Any],
) -> None:
    """Validate answer material and its references without moving it into public props."""

    if component_id not in {
        "didact.matching",
        "didact.sort",
        "didact.categorize",
        "didact.quiz.single-choice",
        "didact.quiz.multi-select",
        "didact.quiz.true-false",
        "didact.quiz.fill-in-the-blank",
        "didact.quiz.short-answer",
        "didact.completion-problem",
        "didact.numeric-question",
        "didact.word-bank",
        "didact.hotspot",
        "didact.label-diagram",
    }:
        return
    evaluation = _record(private.get("evaluation"), f"{component_id}.evaluation")
    mode = evaluation.get("mode")
    if mode != EVALUATED_COMPONENT_MODES[component_id]:
        raise ActivityDefinitionShapeError(
            f"{component_id}.evaluation.mode must be "
            f"{EVALUATED_COMPONENT_MODES[component_id]}"
        )
    if component_id == "didact.numeric-question":
        has_value = "value" in evaluation
        has_range = "min" in evaluation or "max" in evaluation
        if has_value == has_range:
            raise ActivityDefinitionShapeError("numeric evaluation needs one value or one range")
        for key in ("value", "min", "max", "absolute_tolerance", "relative_tolerance"):
            if key in evaluation:
                _number(evaluation[key], f"{component_id}.evaluation.{key}")
        if "min" in evaluation and "max" in evaluation and evaluation["max"] < evaluation["min"]:
            raise ActivityDefinitionShapeError("numeric evaluation max must be >= min")
        return

    if component_id == "didact.hotspot":
        expected = _list(evaluation.get("expected"), "didact.hotspot.evaluation.expected")
        region_ids = {str(item["id"]) for item in _list(public.get("regions"), "regions")}
        if not set(map(str, expected)).issubset(region_ids):
            raise ActivityDefinitionShapeError("hotspot evaluation references unknown regions")
        return

    if component_id == "didact.label-diagram":
        assignments = _record(
            evaluation.get("expected"), "didact.label-diagram.evaluation.expected"
        )
        target_ids = {str(item["id"]) for item in _list(public.get("targets"), "targets")}
        item_ids = {str(item["id"]) for item in _list(public.get("items"), "items")}
        if set(assignments) != target_ids or not set(map(str, assignments.values())).issubset(item_ids):
            raise ActivityDefinitionShapeError("label-diagram evaluation references unknown ids")
        return

    expected = evaluation.get("expected")
    if component_id in {"didact.matching", "didact.categorize", "didact.word-bank"}:
        assignments = _record(expected, f"{component_id}.evaluation.expected")
        source_key = "sources" if component_id == "didact.matching" else "items" if component_id == "didact.categorize" else "gaps"
        target_key = "targets" if component_id == "didact.matching" else "categories" if component_id == "didact.categorize" else "options"
        source_ids = {str(item["id"]) for item in _list(public.get(source_key), source_key)}
        target_ids = {str(item["id"]) for item in _list(public.get(target_key), target_key)}
        if set(assignments) != source_ids or not set(map(str, assignments.values())).issubset(target_ids):
            raise ActivityDefinitionShapeError(f"{component_id}.evaluation references unknown ids")
        return
    if component_id == "didact.sort":
        order = _list(expected, f"{component_id}.evaluation.expected", minimum=2)
        item_ids = {str(item["id"]) for item in _list(public.get("items"), "items", minimum=2)}
        if len(order) != len(set(map(str, order))) or set(map(str, order)) != item_ids:
            raise ActivityDefinitionShapeError("sort evaluation must order every item exactly once")
        return
    if component_id in {"didact.quiz.single-choice", "didact.quiz.multi-select"}:
        option_ids = {str(item["value"]) for item in _list(public.get("options"), "options", minimum=2)}
        selected = expected if isinstance(expected, list) else [expected]
        if not selected or not set(map(str, selected)).issubset(option_ids):
            raise ActivityDefinitionShapeError(f"{component_id}.evaluation references unknown options")
        return
    if component_id == "didact.quiz.true-false":
        if not isinstance(expected, bool):
            raise ActivityDefinitionShapeError("true-false expected value must be boolean")
        return
    if component_id in {"didact.quiz.fill-in-the-blank", "didact.quiz.short-answer"}:
        for index, answer in enumerate(_list(expected, f"{component_id}.evaluation.expected")):
            _text(answer, f"{component_id}.evaluation.expected[{index}]")
        return
    if component_id == "didact.completion-problem":
        answers = _record(expected, f"{component_id}.evaluation.expected")
        completion_ids = {
            str(step["id"])
            for step in _list(public.get("steps"), "steps")
            if step.get("kind") == "completion"
        }
        if set(answers) != completion_ids:
            raise ActivityDefinitionShapeError("completion evaluation must cover every missing step")
        for step_id, accepted in answers.items():
            for index, answer in enumerate(_list(accepted, f"expected.{step_id}")):
                _text(answer, f"expected.{step_id}[{index}]")


__all__ = [
    "AUTHORING_VALIDATORS",
    "AUTHORING_CONTRACTS",
    "AuthoringContract",
    "ActivityDefinitionShapeError",
    "EVALUATED_COMPONENT_MODES",
    "authoring_definition_contract",
    "validate_component_definition",
    "validate_evaluation_definition",
]
