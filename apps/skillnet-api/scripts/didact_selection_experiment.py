"""Reproducible offline experiment over the complete Didact descriptor catalog.

This is deliberately bench-only code.  It compares a full eligible catalog with
bounded facet shortlists and a facet-aware lexical MMR shortlist.  It never calls a
model, the network, or the product runtime.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import statistics
import sys
import time
from typing import Any, Iterable, Mapping, Sequence
import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.personalization.didact_descriptors import export_didact_descriptors  # noqa: E402
from src.personalization.plan import (  # noqa: E402
    AccessibilityCapability,
    CognitiveMission,
    ComponentDescriptor,
    LearningObjective,
    PersonalizationProjection,
    Presentation,
    SourceFunction,
)


BENCH_VERSION = "didact-selection/1"
STRATEGIES: Mapping[str, tuple[str, int | None]] = {
    "eligible-full": ("full", None),
    "facets-k3": ("facets", 3),
    "facets-k5": ("facets", 5),
    "facets-mmr-k5": ("mmr", 5),
}
FACET_WEIGHTS = {
    "source": 0.20,
    "presentation": 0.20,
    "affordance": 0.45,
    "explicit_evidence": 0.10,
    "catalog_rank": 0.05,
}
MMR_LEXICAL_WEIGHT = 0.25
MMR_RELEVANCE_LAMBDA = 0.72

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_STOP_WORDS = frozenset({"a", "an", "and", "component", "for", "of", "the", "to", "with"})


@dataclass(frozen=True, slots=True)
class ExperimentCase:
    case_id: str
    intent_text: str
    query_terms: tuple[str, ...]
    objective: LearningObjective
    projection: PersonalizationProjection
    desired_affordances: frozenset[str]
    desired_evidence_events: frozenset[str]
    relevant_components: frozenset[str]
    prohibited_components: frozenset[str]


def _ratio(matched: int, desired: int) -> float:
    return matched / desired if desired else 1.0


def _tokens(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        separated = _CAMEL_BOUNDARY_RE.sub(" ", value)
        normalized = unicodedata.normalize("NFKD", separated).encode("ascii", "ignore").decode()
        result.extend(
            token
            for token in _TOKEN_RE.findall(normalized.lower().replace("_", " "))
            if token not in _STOP_WORDS
        )
    return tuple(result)


def _parse_case(raw: Mapping[str, Any]) -> ExperimentCase:
    objective = raw["objective"]
    projection = raw.get("projection", {})
    case_id = str(raw["id"]).strip()
    query_terms = tuple(map(str, raw.get("query_terms", [])))
    if not case_id or not query_terms:
        raise ValueError("each case needs a non-empty id and query_terms")
    return ExperimentCase(
        case_id=case_id,
        intent_text=str(raw["intent_text"]),
        query_terms=query_terms,
        objective=LearningObjective(
            objective_id=case_id,
            objective_version=1,
            mission=CognitiveMission(objective["mission"]),
            source_functions=frozenset(
                SourceFunction(value) for value in objective["source_functions"]
            ),
            available_requirements=frozenset(map(str, objective.get("available_requirements", []))),
        ),
        projection=PersonalizationProjection(
            declared_presentations=tuple(
                Presentation(value) for value in projection.get("presentations", [])
            ),
            accessibility_capabilities=frozenset(
                AccessibilityCapability(value) for value in projection.get("accessibility", [])
            ),
        ),
        desired_affordances=frozenset(map(str, raw.get("desired_affordances", []))),
        desired_evidence_events=frozenset(map(str, raw.get("desired_evidence_events", []))),
        relevant_components=frozenset(map(str, raw.get("relevant_components", []))),
        prohibited_components=frozenset(map(str, raw.get("prohibited_components", []))),
    )


def load_manifest(raw: Mapping[str, Any]) -> tuple[ExperimentCase, ...]:
    if raw.get("version") != BENCH_VERSION:
        raise ValueError(f"fixture version must be {BENCH_VERSION!r}")
    cases = tuple(_parse_case(item) for item in raw.get("cases", []))
    if not cases:
        raise ValueError("fixture must contain at least one case")
    ids = [case.case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("case ids must be unique")
    return cases


def eligible_catalog(
    case: ExperimentCase, catalog: Sequence[ComponentDescriptor]
) -> tuple[ComponentDescriptor, ...]:
    """Apply only hard compatibility gates; preference remains a ranking signal."""

    return tuple(
        item
        for item in catalog
        if case.objective.mission in item.missions
        and bool(case.objective.source_functions & item.source_functions)
        and item.requirements <= case.objective.available_requirements
        and case.projection.accessibility_capabilities <= item.accessibility
    )


def _facet_scores(case: ExperimentCase, item: ComponentDescriptor) -> dict[str, float]:
    presentations = frozenset(case.projection.declared_presentations)
    scores = {
        "source": _ratio(
            len(case.objective.source_functions & item.source_functions),
            len(case.objective.source_functions),
        ),
        "presentation": (
            _ratio(len(presentations & item.presentations), len(presentations))
            if presentations
            else 1.0
        ),
        "affordance": _ratio(
            len(case.desired_affordances & item.affordances), len(case.desired_affordances)
        ),
        "explicit_evidence": _ratio(
            len(case.desired_evidence_events & item.evidence_events),
            len(case.desired_evidence_events),
        ),
        "catalog_rank": 1.0 / (1.0 + item.rank),
    }
    scores["total"] = sum(FACET_WEIGHTS[key] * scores[key] for key in FACET_WEIGHTS)
    return scores


def _signature(item: ComponentDescriptor) -> frozenset[str]:
    return frozenset(
        [
            *(f"mission:{value.value}" for value in item.missions),
            *(f"source:{value.value}" for value in item.source_functions),
            *(f"presentation:{value.value}" for value in item.presentations),
            *(f"affordance:{value}" for value in item.affordances),
            *(f"evidence:{value}" for value in item.evidence_events),
            f"producer:{item.producer_kind.value}",
        ]
    )


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _lexical_relevance(
    case: ExperimentCase, eligible: Sequence[ComponentDescriptor]
) -> dict[str, float]:
    documents = {
        item.component_id: _tokens(_signature(item) | {item.component_id}) for item in eligible
    }
    document_frequency = Counter(token for values in documents.values() for token in set(values))
    document_count = len(documents)

    def vector(values: tuple[str, ...]) -> dict[str, float]:
        counts = Counter(values)
        return {
            token: count * (math.log((1 + document_count) / (1 + document_frequency[token])) + 1)
            for token, count in counts.items()
        }

    query = vector(_tokens(case.query_terms))
    query_norm = math.sqrt(sum(value * value for value in query.values()))
    result: dict[str, float] = {}
    for component_id, values in documents.items():
        candidate = vector(values)
        candidate_norm = math.sqrt(sum(value * value for value in candidate.values()))
        numerator = sum(query[token] * candidate[token] for token in set(query) & set(candidate))
        result[component_id] = (
            numerator / (query_norm * candidate_norm) if query_norm and candidate_norm else 0.0
        )
    return result


def rank_candidates(
    strategy: str, case: ExperimentCase, eligible: Sequence[ComponentDescriptor]
) -> tuple[ComponentDescriptor, ...]:
    mode, top_k = STRATEGIES[strategy]
    ordered = sorted(eligible, key=lambda item: (item.rank, item.component_id))
    if mode == "full":
        return tuple(ordered)
    facets = {item.component_id: _facet_scores(case, item) for item in eligible}
    if mode == "facets":
        ordered.sort(key=lambda item: (-facets[item.component_id]["total"], item.component_id))
        return tuple(ordered[:top_k])

    lexical = _lexical_relevance(case, eligible)
    remaining = {item.component_id: item for item in eligible}
    selected: list[ComponentDescriptor] = []
    while remaining and len(selected) < int(top_k or 0):
        best: tuple[float, float, str] | None = None
        for component_id, item in remaining.items():
            relevance = (
                (1.0 - MMR_LEXICAL_WEIGHT) * facets[component_id]["total"]
                + MMR_LEXICAL_WEIGHT * lexical[component_id]
            )
            redundancy = max(
                (_jaccard(_signature(item), _signature(previous)) for previous in selected),
                default=0.0,
            )
            mmr = MMR_RELEVANCE_LAMBDA * relevance - (1.0 - MMR_RELEVANCE_LAMBDA) * redundancy
            candidate = (mmr, relevance, component_id)
            if best is None or candidate[:2] > best[:2] or (
                candidate[:2] == best[:2] and candidate[2] < best[2]
            ):
                best = candidate
        assert best is not None
        selected.append(remaining.pop(best[2]))
    return tuple(selected)


def _pairwise_diversity(selected: Sequence[ComponentDescriptor]) -> float:
    pairs = [
        1.0 - _jaccard(_signature(left), _signature(right))
        for index, left in enumerate(selected)
        for right in selected[index + 1 :]
    ]
    return statistics.fmean(pairs) if pairs else 0.0


def _metrics(case: ExperimentCase, selected: Sequence[ComponentDescriptor]) -> dict[str, Any]:
    selected_ids = frozenset(item.component_id for item in selected)
    affordances = (
        frozenset().union(*(item.affordances for item in selected))
        if selected
        else frozenset()
    )
    evidence = (
        frozenset().union(*(item.evidence_events for item in selected))
        if selected
        else frozenset()
    )
    preferences = frozenset(case.projection.declared_presentations)
    relevant_hits = selected_ids & case.relevant_components
    prohibited_hits = selected_ids & case.prohibited_components
    return {
        "relevant_recall": _ratio(len(relevant_hits), len(case.relevant_components)),
        "relevant_precision": _ratio(len(relevant_hits), len(selected_ids)),
        "affordance_coverage": _ratio(
            len(affordances & case.desired_affordances), len(case.desired_affordances)
        ),
        "explicit_evidence_coverage": _ratio(
            len(evidence & case.desired_evidence_events), len(case.desired_evidence_events)
        ),
        "prohibited_count": len(prohibited_hits),
        "prohibited_rate": _ratio(len(prohibited_hits), len(selected_ids)),
        "preference_match": (
            statistics.fmean(float(bool(item.presentations & preferences)) for item in selected)
            if selected and preferences
            else 1.0
        ),
        "semantic_signature_diversity": _pairwise_diversity(selected),
    }


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index] if ordered else 0.0


def run_experiment(raw: Mapping[str, Any], *, repetitions: int = 200) -> dict[str, Any]:
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    cases = load_manifest(raw)
    catalog = export_didact_descriptors()
    by_id = {item.component_id: item for item in catalog}
    rows: list[dict[str, Any]] = []
    for case in cases:
        referenced = case.relevant_components | case.prohibited_components
        unknown = referenced - by_id.keys()
        if unknown:
            raise ValueError(
                f"case {case.case_id!r} references unknown components: {sorted(unknown)}"
            )
        eligible = eligible_catalog(case, catalog)
        eligible_ids = {item.component_id for item in eligible}
        unreachable = case.relevant_components - eligible_ids
        if unreachable:
            raise ValueError(
                f"case {case.case_id!r} has ineligible relevant components: "
                f"{sorted(unreachable)}"
            )
        for strategy in STRATEGIES:
            samples: list[float] = []
            selected: tuple[ComponentDescriptor, ...] = ()
            for _ in range(repetitions):
                started = time.perf_counter_ns()
                selected = rank_candidates(strategy, case, eligible)
                samples.append((time.perf_counter_ns() - started) / 1_000_000)
            rows.append(
                {
                    "case_id": case.case_id,
                    "strategy": strategy,
                    "eligible_count": len(eligible),
                    "selected": [item.component_id for item in selected],
                    "metrics": _metrics(case, selected),
                    "latency_ms": {
                        "median": statistics.median(samples),
                        "p95": _percentile(samples, 0.95),
                    },
                }
            )

    summaries: dict[str, Any] = {}
    metric_names = (
        "relevant_recall",
        "relevant_precision",
        "affordance_coverage",
        "explicit_evidence_coverage",
        "prohibited_rate",
        "preference_match",
        "semantic_signature_diversity",
    )
    for strategy in STRATEGIES:
        strategy_rows = [row for row in rows if row["strategy"] == strategy]
        summaries[strategy] = {
            "cases": len(strategy_rows),
            **{
                f"mean_{metric}": statistics.fmean(row["metrics"][metric] for row in strategy_rows)
                for metric in metric_names
            },
            "prohibited_total": sum(row["metrics"]["prohibited_count"] for row in strategy_rows),
            "latency_ms": {
                "median": statistics.median(row["latency_ms"]["median"] for row in strategy_rows),
                "p95": _percentile([row["latency_ms"]["p95"] for row in strategy_rows], 0.95),
            },
        }
    return {
        "bench_version": BENCH_VERSION,
        "fixture_id": raw.get("fixture_id"),
        "catalog_size": len(catalog),
        "catalog_explicit_evidence_event_count": sum(len(item.evidence_events) for item in catalog),
        "repetitions": repetitions,
        "strategies": list(STRATEGIES),
        "policy": {
            "facet_weights": FACET_WEIGHTS,
            "mmr_lexical_weight": MMR_LEXICAL_WEIGHT,
            "mmr_relevance_lambda": MMR_RELEVANCE_LAMBDA,
        },
        "summaries": summaries,
        "results": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline Didact selection experiment")
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--repetitions", type=int, default=200)
    args = parser.parse_args()
    report = run_experiment(
        json.loads(args.input.read_text(encoding="utf-8")), repetitions=args.repetitions
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.out:
        args.out.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
