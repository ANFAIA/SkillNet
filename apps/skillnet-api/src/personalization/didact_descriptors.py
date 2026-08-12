"""Pure Didact inventory projection and the fail-closed OpenUI boundary.

The inventory projection deliberately exports all installed Didact types so retrieval
and experimentation can reason over the complete library. Prompt exposure is a second,
stricter operation: only a shortlisted type with an enabled renderer and satisfied host
ports can be translated to an OpenUI schema name.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.personalization.didact_catalog import (
    DidactCatalog,
    DidactComponentAvailability,
    HostPort,
    load_didact_catalog,
)
from src.personalization.plan import (
    AccessibilityCapability,
    CognitiveMission,
    ComponentDescriptor,
    Presentation,
    ProducerKind,
    SourceFunction,
)


class DidactExposureError(ValueError):
    """A requested shortlist cannot safely cross the OpenUI prompt boundary."""


_MISSION_BY_PURPOSE: dict[str, frozenset[CognitiveMission]] = {
    "retrieve": frozenset({CognitiveMission.RECOGNIZE, CognitiveMission.RECONSTRUCT}),
    "practice": frozenset({CognitiveMission.RECONSTRUCT, CognitiveMission.PRODUCE}),
    "assess": frozenset({CognitiveMission.DECIDE, CognitiveMission.PRODUCE}),
    "scaffold": frozenset({CognitiveMission.EXPLAIN, CognitiveMission.RECONSTRUCT}),
    "explain": frozenset({CognitiveMission.EXPLAIN, CognitiveMission.INTERPRET}),
    "explore": frozenset({CognitiveMission.INTERPRET, CognitiveMission.DECIDE}),
    "create": frozenset({CognitiveMission.PRODUCE}),
}

_MISSION_BY_ACTION: dict[str, frozenset[CognitiveMission]] = {
    "inspect": frozenset({CognitiveMission.RECOGNIZE, CognitiveMission.INTERPRET}),
    "respond": frozenset({CognitiveMission.RECONSTRUCT, CognitiveMission.PRODUCE}),
    "select": frozenset({CognitiveMission.DECIDE}),
    "manipulate": frozenset({CognitiveMission.RECONSTRUCT, CognitiveMission.PRODUCE}),
    "construct": frozenset({CognitiveMission.PRODUCE}),
    "compare": frozenset({CognitiveMission.INTERPRET}),
    "explain": frozenset({CognitiveMission.EXPLAIN}),
}

_PRESENTATION_BY_REPRESENTATION: dict[str, Presentation] = {
    "text": Presentation.TEXT,
    "image": Presentation.IMAGE,
    "audio": Presentation.AUDIO,
    "video": Presentation.VIDEO,
    "table": Presentation.TABLE,
    "numeric": Presentation.CHART,
    "data": Presentation.CHART,
    "chart": Presentation.CHART,
    "graph": Presentation.CHART,
    "diagram": Presentation.DIAGRAM,
    "spatial": Presentation.DIAGRAM,
    "simulation": Presentation.SIMULATION,
}


def _missions(component: DidactComponentAvailability) -> frozenset[CognitiveMission]:
    values: set[CognitiveMission] = set()
    for purpose in component.purposes:
        values.update(_MISSION_BY_PURPOSE.get(purpose, ()))
    for action in component.learner_actions:
        values.update(_MISSION_BY_ACTION.get(action, ()))
    return frozenset(values or {CognitiveMission.RECOGNIZE})


def _source_functions(component: DidactComponentAvailability) -> frozenset[SourceFunction]:
    values = {SourceFunction.EXPLORE}
    if "assess" in component.purposes:
        values.add(SourceFunction.ASSESS)
    if any(value in component.capabilities for value in ("response:order", "response:sequence")):
        values.add(SourceFunction.PROCEDURE)
    if any(value.startswith(("data:", "response:numeric")) for value in component.capabilities):
        values.add(SourceFunction.QUANTIFY)
    if any(action in {"compare", "classify", "match"} for action in component.learner_actions):
        values.add(SourceFunction.CONTRAST)
    if any(action in {"locate", "label"} for action in component.learner_actions):
        values.add(SourceFunction.LOCATE)
    return frozenset(values)


def _presentations(component: DidactComponentAvailability) -> frozenset[Presentation]:
    values = {
        presentation
        for representation in component.representations
        if (presentation := _PRESENTATION_BY_REPRESENTATION.get(representation)) is not None
    }
    if HostPort.SIMULATION in component.required_ports:
        values.add(Presentation.SIMULATION)
    return frozenset(values or {Presentation.TEXT})


def _producer(component: DidactComponentAvailability) -> ProducerKind:
    if HostPort.SIMULATION in component.required_ports:
        return ProducerKind.SIMULATION
    if HostPort.ASSETS in component.required_ports or HostPort.MEDIA in component.required_ports:
        return ProducerKind.MEDIA
    if HostPort.EVALUATION in component.required_ports or "assess" in component.purposes:
        return ProducerKind.ASSESSMENT
    if component.required_ports and set(component.required_ports) <= {HostPort.PROGRESS}:
        return ProducerKind.DETERMINISTIC
    return ProducerKind.CONTENT


def _accessibility(component: DidactComponentAvailability) -> frozenset[AccessibilityCapability]:
    values: set[AccessibilityCapability] = set()
    if component.keyboard_access == "full":
        values.add(AccessibilityCapability.KEYBOARD)
    if component.screen_reader_access == "full":
        values.add(AccessibilityCapability.SCREEN_READER)
    if "2.3.3" in component.wcag_criteria:
        values.add(AccessibilityCapability.REDUCED_MOTION)
    return frozenset(values)


def export_didact_descriptors(
    catalog: DidactCatalog | None = None,
    *,
    emittable_only: bool = False,
) -> tuple[ComponentDescriptor, ...]:
    """Project the authoritative inventory into planner descriptors deterministically."""

    source = catalog or load_didact_catalog()
    components = source.emittable if emittable_only else source.components
    return tuple(
        ComponentDescriptor(
            component_id=component.type_id,
            version=1,
            missions=_missions(component),
            source_functions=_source_functions(component),
            presentations=_presentations(component),
            producer_kind=_producer(component),
            affordances=frozenset(component.learner_actions),
            evidence_events=frozenset(
                capability.removeprefix("event:")
                for capability in component.capabilities
                if capability.startswith("event:")
            ),
            requirements=frozenset(port.value for port in component.required_ports),
            accessibility=_accessibility(component),
            rank=100,
        )
        for component in components
    )


def openui_names_for_shortlist(
    type_ids: Iterable[str], catalog: DidactCatalog | None = None
) -> tuple[str, ...]:
    """Translate a Didact shortlist to schema names, refusing unsafe exposure."""

    source = catalog or load_didact_catalog()
    requested = tuple(dict.fromkeys(type_ids))
    unknown = tuple(type_id for type_id in requested if type_id not in source.by_type_id)
    if unknown:
        raise DidactExposureError("unknown Didact types: " + ", ".join(unknown))
    blocked = tuple(
        type_id for type_id in requested if not source.by_type_id[type_id].llm_emittable
    )
    if blocked:
        details = ", ".join(
            f"{type_id}({source.by_type_id[type_id].availability_status.value},"
            f"{source.by_type_id[type_id].emission_status.value})"
            for type_id in blocked
        )
        raise DidactExposureError("Didact shortlist is not OpenUI-emittable: " + details)
    return tuple(source.by_type_id[type_id].renderer_symbol for type_id in requested)  # type: ignore[misc]


__all__ = [
    "DidactExposureError",
    "export_didact_descriptors",
    "openui_names_for_shortlist",
]
