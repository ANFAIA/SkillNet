"""Offline experiment: prepare Didact opportunities while creating a course.

All 34 installed types remain in the considered universe.  Each arm persists only a
small, grounded and expandable option set per node.  Nothing here is connected to the
course creation graph or runtime renderer.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.personalization.didact_catalog import load_didact_catalog
from src.personalization.didact_descriptors import export_didact_descriptors
from src.personalization.experience_opportunities import (
    AdaptationAxis,
    ExperienceOpportunity,
    NodeExperienceOpportunities,
    OpportunityReadiness,
)
from src.personalization.plan import (
    CognitiveMission,
    Presentation,
    SourceFunction,
)

BENCH_VERSION = "didact-creation-opportunities/1"
STRATEGIES: Mapping[str, tuple[int, float]] = {
    "relevance-k5": (5, 1.0),
    "balanced-k5": (5, 0.72),
    "exploratory-k8": (8, 0.55),
}
_TOKEN = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class NodeCase:
    node_id: str
    mission: CognitiveMission
    source_functions: frozenset[SourceFunction]
    query_terms: tuple[str, ...]
    atom_refs: tuple[str, ...]


def _case(raw: Mapping[str, Any]) -> NodeCase:
    objective = raw["objective"]
    node_id = str(raw["id"])
    return NodeCase(
        node_id=node_id,
        mission=CognitiveMission(objective["mission"]),
        source_functions=frozenset(SourceFunction(x) for x in objective["source_functions"]),
        query_terms=tuple(str(x) for x in raw.get("query_terms", ())),
        # The bench models references, never invented instructional prose.  A production
        # generator would copy these stable ids from NodeKnowledgePack atoms.
        atom_refs=(f"{node_id}:must-preserve", f"{node_id}:selectable"),
    )


def load_cases(raw: Mapping[str, Any]) -> tuple[NodeCase, ...]:
    cases = tuple(_case(item) for item in raw.get("cases", ()))
    if not cases:
        raise ValueError("fixture must contain cases")
    return cases


def _tokens(*values: str) -> frozenset[str]:
    return frozenset(token for value in values for token in _TOKEN.findall(value.lower()))


def _signature(item: Any) -> frozenset[str]:
    return frozenset(
        [
            *(f"m:{x.value}" for x in item.missions),
            *(f"s:{x.value}" for x in item.source_functions),
            *(f"p:{x.value}" for x in item.presentations),
            *(f"a:{x}" for x in item.affordances),
            f"producer:{item.producer_kind.value}",
        ]
    )


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _relevance(case: NodeCase, item: Any) -> float:
    mission = float(case.mission in item.missions)
    source = len(case.source_functions & item.source_functions) / len(case.source_functions)
    query = _tokens(*case.query_terms)
    candidate = _tokens(item.component_id, *item.affordances, *(x.value for x in item.presentations))
    lexical = _jaccard(query, candidate)
    return 0.50 * mission + 0.35 * source + 0.15 * lexical


def _select(case: NodeCase, catalog: Sequence[Any], *, k: int, relevance_weight: float) -> tuple[Any, ...]:
    remaining = {item.component_id: item for item in catalog}
    selected: list[Any] = []
    while remaining and len(selected) < k:
        ranked = []
        for component_id, item in remaining.items():
            redundancy = max(
                (_jaccard(_signature(item), _signature(previous)) for previous in selected),
                default=0.0,
            )
            score = relevance_weight * _relevance(case, item) - (1 - relevance_weight) * redundancy
            ranked.append((score, _relevance(case, item), component_id, item))
        chosen = max(ranked, key=lambda row: (row[0], row[1], row[2]))[3]
        selected.append(chosen)
        remaining.pop(chosen.component_id)
    return tuple(selected)


def _readiness(type_id: str, availability: Any) -> OpportunityReadiness:
    component = availability[type_id]
    if component.llm_emittable:
        return OpportunityReadiness.READY
    if component.missing_ports:
        return OpportunityReadiness.NEEDS_HOST_PORT
    return OpportunityReadiness.NEEDS_AUTHORING


def _artifact(case: NodeCase, selected: Sequence[Any], strategy: str) -> NodeExperienceOpportunities:
    catalog = load_didact_catalog()
    by_type = catalog.by_type_id
    return NodeExperienceOpportunities(
        node_id=case.node_id,
        schema_version=1,
        knowledge_pack_hash="1" * 64,
        catalog_content_hash=catalog.content_sha256,
        catalog_type_ids=tuple(item.type_id for item in catalog.components),
        strategy=strategy,
        opportunities=tuple(
            ExperienceOpportunity(
                opportunity_id=f"{case.node_id}:{item.component_id}",
                component_type_id=item.component_id,
                pedagogical_role=f"{case.mission.value}:{item.producer_kind.value}",
                grounding_atom_refs=case.atom_refs,
                rationale_codes=("mission-fit", "source-function-fit"),
                required_ports=tuple(sorted(item.requirements)),
                adaptation_axes=(
                    AdaptationAxis.SUPPORT,
                    AdaptationAxis.DENSITY,
                    AdaptationAxis.PRESENTATION,
                    AdaptationAxis.ERROR_RECOVERY,
                    AdaptationAxis.CHALLENGE,
                ),
                readiness=_readiness(item.component_id, by_type),
            )
            for item in selected
        ),
    )


def _personalized_top3(selected: Sequence[Any], presentation: Presentation) -> tuple[str, ...]:
    ranked = sorted(
        selected,
        key=lambda item: (
            -(1 if presentation in item.presentations else 0),
            item.component_id,
        ),
    )
    return tuple(item.component_id for item in ranked[:3])


def run_experiment(raw: Mapping[str, Any]) -> dict[str, Any]:
    cases = load_cases(raw)
    catalog = export_didact_descriptors()
    if len(catalog) != 34:
        raise ValueError(f"expected all 34 Didact types, got {len(catalog)}")
    rows: list[dict[str, Any]] = []
    for case in cases:
        for strategy, (k, relevance_weight) in STRATEGIES.items():
            selected = _select(case, catalog, k=k, relevance_weight=relevance_weight)
            artifact = _artifact(case, selected, strategy)
            text_top3 = _personalized_top3(selected, Presentation.TEXT)
            visual_top3 = _personalized_top3(selected, Presentation.DIAGRAM)
            rows.append(
                {
                    "node_id": case.node_id,
                    "strategy": strategy,
                    "considered_catalog_size": len(artifact.catalog_type_ids),
                    "selected": [item.component_id for item in selected],
                    "grounding_rate": statistics.fmean(
                        bool(item.grounding_atom_refs) for item in artifact.opportunities
                    ),
                    "semantic_diversity": statistics.fmean(
                        1 - _jaccard(_signature(left), _signature(right))
                        for index, left in enumerate(selected)
                        for right in selected[index + 1 :]
                    ),
                    "artifact_bytes": len(artifact.canonical_json().encode()),
                    "estimated_context_tokens": math.ceil(len(artifact.canonical_json()) / 4),
                    "later_personalization_delta": 1 - _jaccard(
                        frozenset(text_top3), frozenset(visual_top3)
                    ),
                    "readiness": dict(Counter(item.readiness.value for item in artifact.opportunities)),
                    "artifact_hash": artifact.canonical_hash,
                }
            )

    summaries = {}
    for strategy in STRATEGIES:
        strategy_rows = [row for row in rows if row["strategy"] == strategy]
        union = {component for row in strategy_rows for component in row["selected"]}
        summaries[strategy] = {
            "nodes": len(strategy_rows),
            "catalog_coverage": len(union) / len(catalog),
            "unique_components_suggested": len(union),
            "mean_grounding_rate": statistics.fmean(row["grounding_rate"] for row in strategy_rows),
            "mean_semantic_diversity": statistics.fmean(row["semantic_diversity"] for row in strategy_rows),
            "mean_estimated_context_tokens": statistics.fmean(
                row["estimated_context_tokens"] for row in strategy_rows
            ),
            "mean_later_personalization_delta": statistics.fmean(
                row["later_personalization_delta"] for row in strategy_rows
            ),
        }
    return {
        "bench_version": BENCH_VERSION,
        "fixture_id": raw.get("fixture_id"),
        "catalog_size": len(catalog),
        "strategies": list(STRATEGIES),
        "summaries": summaries,
        "results": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = run_experiment(json.loads(args.input.read_text(encoding="utf-8")))
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.out:
        args.out.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
