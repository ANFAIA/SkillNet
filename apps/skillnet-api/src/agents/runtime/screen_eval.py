"""Deterministic, catalogue-agnostic evaluation of generated learning screens.

The runtime validator answers "can this OpenUI program render?".  This module answers
different questions: did the planned learning action survive assembly, is critical
information reachable, and does a corpus use meaningfully different structures?

All pedagogical expectations are supplied by the scenario.  Component names are treated
as opaque labels so adding or replacing the component library does not require changing
the evaluator.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import itertools
import re
import unicodedata
from typing import Any, Iterable, Mapping, Sequence


_WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class CriticalFact:
    """A required fact; any normalized phrase in ``any_of`` is sufficient."""

    id: str
    any_of: tuple[str, ...]


@dataclass(frozen=True)
class ScreenScenario:
    id: str
    objective: str
    ui_spec: Mapping[str, Any]
    blueprint: Mapping[str, Any] | None = None
    central_intents: tuple[str, ...] = ("concepto",)
    critical_facts: tuple[CriticalFact, ...] = ()


@dataclass(frozen=True)
class ScreenMetrics:
    id: str
    objective: str
    component_count: int
    reachable_count: int
    unreachable_ids: tuple[str, ...]
    reachable_types: tuple[str, ...]
    planned_count: int
    planned_reachable_count: int
    planned_reachability: float | None
    orphan_reachable_ids: tuple[str, ...]
    central_block_ids: tuple[str, ...]
    central_reachable_ids: tuple[str, ...]
    central_mission_score: float | None
    redundant_pairs: tuple[tuple[str, str], ...]
    redundancy_score: float
    critical_fact_hits: tuple[str, ...]
    critical_fact_misses: tuple[str, ...]
    critical_preservation: float | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CorpusMetrics:
    screen_count: int
    objective_count: int
    distinct_signatures: int
    signature_ratio: float
    cross_objective_diversity: float | None
    same_objective_stability: float | None
    mean_central_mission_score: float | None
    mean_redundancy_score: float
    mean_critical_preservation: float | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalized(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value).lower())
    return " ".join(_WORD_RE.findall("".join(c for c in text if not unicodedata.combining(c))))


def _component_index(spec: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    components = spec.get("components", [])
    if not isinstance(components, list):
        return {}
    return {
        str(component["id"]): component
        for component in components
        if isinstance(component, Mapping) and component.get("id") is not None
    }


def reachable_component_ids(spec: Mapping[str, Any]) -> tuple[str, ...]:
    """Return a stable depth-first traversal of components reachable from ``root``."""

    index = _component_index(spec)
    root = spec.get("root")
    if root is None or str(root) not in index:
        return ()

    ordered: list[str] = []
    pending = [str(root)]
    seen: set[str] = set()
    while pending:
        component_id = pending.pop()
        if component_id in seen or component_id not in index:
            continue
        seen.add(component_id)
        ordered.append(component_id)
        children = index[component_id].get("children", [])
        if isinstance(children, list):
            pending.extend(reversed([str(child) for child in children]))
    return tuple(ordered)


def _text_tokens(component: Mapping[str, Any]) -> set[str]:
    def strings(value: Any) -> Iterable[str]:
        if isinstance(value, str):
            yield value
        elif isinstance(value, Mapping):
            for key, child in value.items():
                if key not in {"id", "type", "children"}:
                    yield from strings(child)
        elif isinstance(value, list):
            for child in value:
                yield from strings(child)

    return set(_WORD_RE.findall(_normalized(" ".join(strings(component)))))


def _similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _blueprint_blocks(blueprint: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if not blueprint:
        return []
    blocks = blueprint.get("blocks", [])
    if not isinstance(blocks, list):
        return []
    return [block for block in blocks if isinstance(block, Mapping)]


def evaluate_screen(
    scenario: ScreenScenario,
    *,
    redundancy_threshold: float = 0.72,
) -> ScreenMetrics:
    """Evaluate one final screen against its declared pedagogical scenario."""

    index = _component_index(scenario.ui_spec)
    reachable = reachable_component_ids(scenario.ui_spec)
    reachable_set = set(reachable)
    unreachable = tuple(component_id for component_id in index if component_id not in reachable_set)
    reachable_types = tuple(str(index[i].get("type", "")) for i in reachable if index[i].get("type"))

    blocks = _blueprint_blocks(scenario.blueprint)
    planned_ids = tuple(str(block["id"]) for block in blocks if block.get("id") is not None)
    planned_set = set(planned_ids)
    planned_reachable = tuple(i for i in planned_ids if i in reachable_set)
    planned_ratio = len(planned_reachable) / len(planned_ids) if planned_ids else None
    root_id = str(scenario.ui_spec.get("root", ""))
    orphans = (
        tuple(i for i in reachable if i != root_id and i not in planned_set)
        if blocks
        else ()
    )

    central = tuple(
        str(block["id"])
        for block in blocks
        if block.get("id") is not None and str(block.get("intent", "")) in scenario.central_intents
    )
    central_reachable = tuple(i for i in central if i in reachable_set)
    if not blocks:
        central_score = None
    elif len(central) == 1 and central_reachable == central:
        central_score = 1.0
    elif central:
        central_score = len(central_reachable) / len(central) / len(central)
    else:
        central_score = 0.0

    content_ids = tuple(i for i in reachable if i != root_id)
    tokens = {i: _text_tokens(index[i]) for i in content_ids}
    redundant = tuple(
        (left, right)
        for left, right in itertools.combinations(content_ids, 2)
        if _similarity(tokens[left], tokens[right]) >= redundancy_threshold
    )
    possible_pairs = len(content_ids) * (len(content_ids) - 1) // 2
    redundancy_score = len(redundant) / possible_pairs if possible_pairs else 0.0

    reachable_text = _normalized(" ".join(str(index[i]) for i in reachable))
    hits: list[str] = []
    misses: list[str] = []
    for fact in scenario.critical_facts:
        found = any(_normalized(phrase) in reachable_text for phrase in fact.any_of)
        (hits if found else misses).append(fact.id)
    preservation = len(hits) / len(scenario.critical_facts) if scenario.critical_facts else None

    return ScreenMetrics(
        id=scenario.id,
        objective=scenario.objective,
        component_count=len(index),
        reachable_count=len(reachable),
        unreachable_ids=unreachable,
        reachable_types=reachable_types,
        planned_count=len(planned_ids),
        planned_reachable_count=len(planned_reachable),
        planned_reachability=planned_ratio,
        orphan_reachable_ids=orphans,
        central_block_ids=central,
        central_reachable_ids=central_reachable,
        central_mission_score=central_score,
        redundant_pairs=redundant,
        redundancy_score=redundancy_score,
        critical_fact_hits=tuple(hits),
        critical_fact_misses=tuple(misses),
        critical_preservation=preservation,
    )


def _jaccard_distance(left: set[str], right: set[str]) -> float:
    union = left | right
    return 1.0 - len(left & right) / len(union) if union else 0.0


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def evaluate_corpus(
    screens: Sequence[ScreenMetrics], *, ignore_types: Iterable[str] = ()
) -> CorpusMetrics:
    """Summarize focus, safety and structural diversity over multiple objectives."""

    ignored = set(ignore_types)
    signatures = [set(screen.reachable_types) - ignored for screen in screens]
    cross: list[float] = []
    same: list[float] = []
    for (left, left_signature), (right, right_signature) in itertools.combinations(
        zip(screens, signatures, strict=True), 2
    ):
        distance = _jaccard_distance(left_signature, right_signature)
        if left.objective == right.objective:
            same.append(1.0 - distance)
        else:
            cross.append(distance)

    mission = [s.central_mission_score for s in screens if s.central_mission_score is not None]
    critical = [s.critical_preservation for s in screens if s.critical_preservation is not None]
    frozen_signatures = {tuple(sorted(signature)) for signature in signatures}
    return CorpusMetrics(
        screen_count=len(screens),
        objective_count=len({s.objective for s in screens}),
        distinct_signatures=len(frozen_signatures),
        signature_ratio=len(frozen_signatures) / len(screens) if screens else 0.0,
        cross_objective_diversity=_mean(cross),
        same_objective_stability=_mean(same),
        mean_central_mission_score=_mean(mission),
        mean_redundancy_score=_mean([s.redundancy_score for s in screens]) or 0.0,
        mean_critical_preservation=_mean(critical),
    )
