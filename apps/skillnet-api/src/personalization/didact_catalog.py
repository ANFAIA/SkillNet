"""SkillNet's availability view over the pinned Didact snapshot.

This module answers *what is installed and what can the host currently execute*.  It
deliberately does not answer *what should OpenUI see for this node*.  That latter
question belongs to an exposure policy and may change between experiments without
removing anything from this catalogue.

The 34 educational types are read from Didact's authoritative ``availableTypes``
snapshot.  We only maintain the small, honest integration delta here: renderers which
SkillNet has actually adapted and host ports which those renderers can use.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

SNAPSHOT_PATH = Path(__file__).with_name("didact_snapshot.json")


class DidactCatalogError(ValueError):
    """The pinned snapshot cannot produce a trustworthy catalogue."""


class HostPort(StrEnum):
    """Stable host capabilities used by families of Didact components."""

    ASSETS = "assets"
    CLOCK = "clock"
    EVALUATION = "evaluation"
    EVENTS = "events"
    EXECUTION = "execution"
    MEDIA = "media"
    PERSISTENCE = "persistence"
    PROGRESS = "progress"
    SCHEDULER = "scheduler"
    SIMULATION = "simulation"


class AvailabilityStatus(StrEnum):
    """Whether the SkillNet host can execute an installed renderer."""

    READY = "ready"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


class EmissionStatus(StrEnum):
    """Explicit permission for OpenUI, independent from renderer readiness."""

    ENABLED = "enabled"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class DidactComponentAvailability:
    """One Didact educational type as understood by the SkillNet host."""

    type_id: str
    manifest_id: str
    export_name: str
    registry_item: str
    name: str
    description: str
    maturity: str
    component_version: str
    renderer_available: bool
    renderer_symbol: str | None
    availability_status: AvailabilityStatus
    emission_status: EmissionStatus
    required_ports: tuple[HostPort, ...]
    missing_ports: tuple[HostPort, ...]
    capabilities: tuple[str, ...]
    purposes: tuple[str, ...]
    learner_actions: tuple[str, ...]
    representations: tuple[str, ...]
    keyboard_access: str
    screen_reader_access: str
    wcag_criteria: tuple[str, ...]

    @property
    def llm_emittable(self) -> bool:
        return (
            self.availability_status is not AvailabilityStatus.BLOCKED
            and self.emission_status is EmissionStatus.ENABLED
        )


@dataclass(frozen=True, slots=True)
class DidactCatalog:
    """Complete installed inventory; never a prompt shortlist."""

    source_repository: str
    source_commit: str
    content_sha256: str
    components: tuple[DidactComponentAvailability, ...]

    @property
    def by_type_id(self) -> dict[str, DidactComponentAvailability]:
        return {component.type_id: component for component in self.components}

    @property
    def emittable(self) -> tuple[DidactComponentAvailability, ...]:
        """Host-ready entries, still unfiltered by any OpenUI exposure experiment."""

        return tuple(
            component
            for component in self.components
            if component.llm_emittable
        )


# This is an adapter registry, not a second copy of Didact's inventory.  An entry only
# appears after a real SkillNet renderer exists.  The snapshot remains the source of
# truth for all type ids and metadata.
_RENDERER_BINDINGS: Mapping[str, str] = {
    "didact.flashcard": "Flashcard",
    "didact.hint-reveal": "HintReveal",
    "didact.glossary-term": "DidactGlossary",
    "didact.timeline-steps": "DidactTimeline",
    "didact.worked-example": "DidactWorkedExample",
    # Generic server-owned ActivityDefinition renderer. These bindings mirror the
    # adapters in DidactActivityBlock exactly; an installed React export alone is not
    # sufficient reason to expose a component to generation.
    "didact.rubric": "DidactActivity",
    "didact.data-explorer": "DidactActivity",
    "didact.self-explanation-prompt": "DidactActivity",
    "didact.concept-map": "DidactActivity",
    "didact.drawing-response": "DidactActivity",
    "didact.equation-workbench": "DidactActivity",
    "didact.evidence-annotation": "DidactActivity",
    "didact.measurement-lab": "DidactActivity",
}

# A renderer may exist before SkillNet has the host contract needed to expose it.
# Self-explanation captures learner-authored work; losing it on navigation is not an
# honest implementation, so persistence remains required despite the ungraded result.
_HOST_REQUIREMENT_OVERRIDES: Mapping[str, frozenset[HostPort]] = {
    "didact.self-explanation-prompt": frozenset({HostPort.PERSISTENCE}),
    "didact.concept-map": frozenset({HostPort.PERSISTENCE}),
    "didact.drawing-response": frozenset({HostPort.PERSISTENCE}),
    "didact.evidence-annotation": frozenset({HostPort.PERSISTENCE}),
    "didact.equation-workbench": frozenset({HostPort.EVALUATION}),
    "didact.measurement-lab": frozenset({HostPort.EVALUATION}),
}

# Ports currently satisfied by a shared SkillNet host adapter.  Local-only components
# need no port, so Flashcard and HintReveal are enabled without pretending that the
# evaluation/media/simulation adapters already exist.
_AVAILABLE_HOST_PORTS: frozenset[HostPort] = frozenset(
    {HostPort.CLOCK, HostPort.EVALUATION, HostPort.PERSISTENCE}
)


def _strings(value: object, *, field: str, owner: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise DidactCatalogError(f"{owner}.{field} must be an array of strings")
    return tuple(value)


def _required_ports(manifest: Mapping[str, Any]) -> tuple[HostPort, ...]:
    """Infer shared host contracts from semantic manifest data, not component names.

    These rules intentionally operate on capabilities, authoring fields, tags and
    optional dependencies.  A newly added Didact type therefore receives the same host
    requirements as its peers without adding a 35th manual mapping.
    """

    capabilities = tuple(str(value).lower() for value in manifest.get("capabilities", []))
    tags = tuple(str(value).lower() for value in manifest.get("tags", []))
    dependencies = tuple(
        str(value).lower()
        for dependency in manifest.get("optionalDependencies", [])
        if isinstance(dependency, Mapping)
        for value in (dependency.get("package", ""), dependency.get("purpose", ""))
    )
    authoring = manifest.get("authoring", {})
    fields = authoring.get("fields", []) if isinstance(authoring, Mapping) else []
    field_ids = {
        str(field.get("id", field.get("name", ""))).lower()
        for field in fields
        if isinstance(field, Mapping)
    }
    ports: set[HostPort] = set()
    if (
        any(cap in capabilities for cap in ("result:scored", "result:partial-credit"))
        or any(cap.startswith("evaluation:") for cap in capabilities)
        or field_ids.intersection({"solution", "solutions", "answer_key", "scoring"})
    ):
        ports.add(HostPort.EVALUATION)
    if any(cap in capabilities for cap in ("display:completion", "display:mastery")):
        ports.add(HostPort.PROGRESS)
    if (
        any(cap.startswith("media:") for cap in capabilities)
        or any(
            tag in {"media", "interactive-media", "interactive-audio", "interactive-video"}
            for tag in tags
        )
        or any("media-player" in dependency for dependency in dependencies)
    ):
        ports.add(HostPort.ASSETS)
    if any(cap.startswith("execution:") for cap in capabilities) or "sandbox" in tags:
        ports.add(HostPort.EXECUTION)
    if any(cap.startswith("simulation:") for cap in capabilities) or "simulation" in tags:
        ports.add(HostPort.SIMULATION)
    if (
        any(cap.startswith("scheduling:") for cap in capabilities)
        or "spaced-repetition" in tags
        or any("fsrs" in dependency or "scheduling" in dependency for dependency in dependencies)
    ):
        ports.update((HostPort.PERSISTENCE, HostPort.SCHEDULER))

    return tuple(sorted(ports, key=str))


def _manifest_index(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    manifests = payload.get("manifests")
    if not isinstance(manifests, list):
        raise DidactCatalogError("snapshot.manifests must be an array")
    index: dict[str, Mapping[str, Any]] = {}
    for manifest in manifests:
        if not isinstance(manifest, Mapping) or not isinstance(manifest.get("id"), str):
            raise DidactCatalogError("every manifest must be an object with a string id")
        manifest_id = manifest["id"]
        if manifest_id in index:
            raise DidactCatalogError(f"duplicate manifest id: {manifest_id}")
        index[manifest_id] = manifest
    return index


def _availability(
    raw_type: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    available_ports: frozenset[HostPort],
) -> DidactComponentAvailability:
    type_id = raw_type.get("id")
    manifest_id = raw_type.get("manifest_id")
    export_name = raw_type.get("export_name")
    registry_item = raw_type.get("registry_item")
    if not all(isinstance(value, str) and value for value in (type_id, manifest_id, export_name)):
        raise DidactCatalogError("every available type needs id, manifest_id and export_name")
    if not isinstance(registry_item, str):
        registry_item = ""

    lifecycle = manifest.get("lifecycle", {})
    version = manifest.get("version", {})
    facets = manifest.get("facets", {})
    accessibility = manifest.get("accessibility", {})
    if not isinstance(lifecycle, Mapping) or not isinstance(version, Mapping):
        raise DidactCatalogError(f"{manifest_id} needs lifecycle and version objects")
    if not isinstance(facets, Mapping):
        raise DidactCatalogError(f"{manifest_id}.facets must be an object")
    if not isinstance(accessibility, Mapping):
        raise DidactCatalogError(f"{manifest_id}.accessibility must be an object")

    required_ports = tuple(
        sorted(
            set(_required_ports(manifest)) | set(_HOST_REQUIREMENT_OVERRIDES.get(type_id, ())),
            key=str,
        )
    )
    missing_ports = tuple(port for port in required_ports if port not in available_ports)
    renderer_symbol = _RENDERER_BINDINGS.get(type_id)
    renderer_available = renderer_symbol is not None
    availability_status = (
        AvailabilityStatus.BLOCKED
        if not renderer_available or missing_ports
        else AvailabilityStatus.READY
    )
    emission_status = EmissionStatus.ENABLED if renderer_available and not missing_ports else EmissionStatus.DISABLED

    return DidactComponentAvailability(
        type_id=type_id,
        manifest_id=manifest_id,
        export_name=export_name,
        registry_item=registry_item,
        name=str(manifest.get("name", export_name)),
        description=str(manifest.get("description", "")),
        maturity=str(lifecycle.get("maturity", "unknown")),
        component_version=str(version.get("component", "unknown")),
        renderer_available=renderer_available,
        renderer_symbol=renderer_symbol,
        availability_status=availability_status,
        emission_status=emission_status,
        required_ports=required_ports,
        missing_ports=missing_ports,
        capabilities=_strings(
            manifest.get("capabilities", []), field="capabilities", owner=manifest_id
        ),
        purposes=_strings(facets.get("purposes", []), field="purposes", owner=manifest_id),
        learner_actions=_strings(
            facets.get("learnerActions", []), field="learnerActions", owner=manifest_id
        ),
        representations=_strings(
            facets.get("representations", []), field="representations", owner=manifest_id
        ),
        keyboard_access=str(accessibility.get("keyboard", "unknown")),
        screen_reader_access=str(accessibility.get("screenReader", "unknown")),
        wcag_criteria=_strings(
            accessibility.get("wcagCriteria", []), field="wcagCriteria", owner=manifest_id
        ),
    )


def load_didact_catalog(
    path: Path = SNAPSHOT_PATH,
    *,
    available_ports: Iterable[HostPort] = _AVAILABLE_HOST_PORTS,
) -> DidactCatalog:
    """Load and validate the complete neutral snapshot into host availability state."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DidactCatalogError(f"cannot read Didact snapshot at {path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise DidactCatalogError("Didact snapshot root must be an object")

    raw_types = payload.get("available_types")
    if not isinstance(raw_types, list):
        raise DidactCatalogError("snapshot.available_types must be an array")
    manifest_by_id = _manifest_index(payload)
    port_set = frozenset(available_ports)

    seen: set[str] = set()
    components: list[DidactComponentAvailability] = []
    for raw_type in raw_types:
        if not isinstance(raw_type, Mapping):
            raise DidactCatalogError("every available type must be an object")
        type_id = raw_type.get("id")
        manifest_id = raw_type.get("manifest_id")
        if not isinstance(type_id, str) or type_id in seen:
            raise DidactCatalogError(f"duplicate or invalid available type id: {type_id!r}")
        if not isinstance(manifest_id, str) or manifest_id not in manifest_by_id:
            raise DidactCatalogError(f"{type_id} references unknown manifest {manifest_id!r}")
        seen.add(type_id)
        components.append(
            _availability(raw_type, manifest_by_id[manifest_id], available_ports=port_set)
        )

    counts = payload.get("counts", {})
    declared_count = counts.get("available_types") if isinstance(counts, Mapping) else None
    if declared_count != len(components):
        raise DidactCatalogError(
            f"snapshot declares {declared_count} available types but contains {len(components)}"
        )
    source = payload.get("source", {})
    if not isinstance(source, Mapping):
        raise DidactCatalogError("snapshot.source must be an object")

    return DidactCatalog(
        source_repository=str(source.get("repository", "")),
        source_commit=str(source.get("commit", "")),
        content_sha256=str(payload.get("content_sha256", "")),
        components=tuple(components),
    )
