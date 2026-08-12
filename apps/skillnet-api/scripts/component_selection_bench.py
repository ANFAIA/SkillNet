"""Offline benchmark for bounded OpenUI/Didact component selection.

The benchmark deliberately does not participate in the runtime.  It reuses the
canonical personalization types and the explicit legacy OpenUI adapter, then compares
small, pure selection policies over a versioned fixture.

Usage::

    uv run python scripts/component_selection_bench.py \
        tests/fixtures/component-selection-v1.json

No database, network connection, embedding model or LLM is used.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
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

from src.personalization.legacy_openui_catalog import (  # noqa: E402
    adapt_legacy_openui_catalog,
)
from src.personalization.plan import (  # noqa: E402
    AccessibilityCapability,
    CognitiveMission,
    ComponentDescriptor,
    LearningObjective,
    PersonalizationProjection,
    Presentation,
    SourceFunction,
)
from src.render.prompt import catalog_version  # noqa: E402


BENCH_VERSION = "component-selection/1"
STRATEGIES = ("eligible-full", "facets-top-k", "lexical-diverse-top-k")
FACET_WEIGHTS = {
    "source": 0.30,
    "presentation": 0.15,
    "affordance": 0.30,
    "evidence": 0.20,
    "catalog_rank": 0.05,
}
LEXICAL_RELEVANCE_WEIGHT = 0.80
LEXICAL_NOVELTY_WEIGHT = 0.20

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "component",
        "for",
        "of",
        "the",
        "to",
        "with",
    }
)


@dataclass(frozen=True, slots=True)
class SelectionCase:
    case_id: str
    intent_text: str
    query_terms: tuple[str, ...]
    objective: LearningObjective
    projection: PersonalizationProjection
    desired_affordances: frozenset[str]
    desired_evidence_events: frozenset[str]
    relevant_components: frozenset[str]
    forbidden_components: frozenset[str]


@dataclass(frozen=True, slots=True)
class FilterStep:
    name: str
    before: int
    after: int
    rejected: tuple[str, ...]


def _tokens(values: Iterable[str]) -> tuple[str, ...]:
    tokens: list[str] = []
    for value in values:
        separated = _CAMEL_BOUNDARY_RE.sub(" ", value)
        normalized = unicodedata.normalize("NFKD", separated).encode("ascii", "ignore").decode()
        tokens.extend(
            token
            for token in _TOKEN_RE.findall(normalized.lower().replace("_", " "))
            if token not in _STOP_WORDS
        )
    return tuple(tokens)


def _ratio(matched: int, desired: int) -> float:
    return matched / desired if desired else 1.0


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = math.ceil(percentile * len(ordered)) - 1
    return ordered[max(0, min(index, len(ordered) - 1))]


def _parse_case(raw: Mapping[str, Any]) -> SelectionCase:
    raw_objective = raw["objective"]
    raw_projection = raw.get("projection", {})
    case_id = str(raw["id"]).strip()
    query_terms = tuple(map(str, raw.get("query_terms", [])))
    if not case_id or not query_terms:
        raise ValueError("each case needs a non-empty id and query_terms")
    return SelectionCase(
        case_id=case_id,
        intent_text=str(raw["intent_text"]),
        query_terms=query_terms,
        objective=LearningObjective(
            objective_id=case_id,
            objective_version=1,
            mission=CognitiveMission(raw_objective["mission"]),
            source_functions=frozenset(
                SourceFunction(value) for value in raw_objective["source_functions"]
            ),
            available_requirements=frozenset(
                map(str, raw_objective.get("available_requirements", []))
            ),
        ),
        projection=PersonalizationProjection(
            declared_presentations=tuple(
                Presentation(value) for value in raw_projection.get("presentations", [])
            ),
            accessibility_capabilities=frozenset(
                AccessibilityCapability(value) for value in raw_projection.get("accessibility", [])
            ),
        ),
        desired_affordances=frozenset(map(str, raw.get("desired_affordances", []))),
        desired_evidence_events=frozenset(map(str, raw.get("desired_evidence_events", []))),
        relevant_components=frozenset(map(str, raw.get("relevant_components", []))),
        forbidden_components=frozenset(map(str, raw.get("forbidden_components", []))),
    )


def load_manifest(raw: Mapping[str, Any]) -> tuple[int, tuple[SelectionCase, ...]]:
    if raw.get("version") != BENCH_VERSION:
        raise ValueError(f"fixture version must be {BENCH_VERSION!r}")
    top_k = int(raw.get("top_k", 5))
    if top_k < 1:
        raise ValueError("top_k must be positive")
    cases = tuple(_parse_case(item) for item in raw.get("cases", []))
    if not cases:
        raise ValueError("fixture must contain at least one case")
    ids = [case.case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("case ids must be unique")
    return top_k, cases


def filter_catalog(
    case: SelectionCase, catalog: tuple[ComponentDescriptor, ...]
) -> tuple[tuple[ComponentDescriptor, ...], tuple[FilterStep, ...]]:
    remaining = catalog
    filters = (
        ("mission", lambda item: case.objective.mission in item.missions),
        (
            "source_function",
            lambda item: bool(case.objective.source_functions & item.source_functions),
        ),
        (
            "requirements",
            lambda item: item.requirements <= case.objective.available_requirements,
        ),
        (
            "accessibility",
            lambda item: case.projection.accessibility_capabilities <= item.accessibility,
        ),
    )
    steps: list[FilterStep] = []
    for name, predicate in filters:
        before = len(remaining)
        rejected = tuple(item.component_id for item in remaining if not predicate(item))
        remaining = tuple(item for item in remaining if predicate(item))
        steps.append(FilterStep(name, before, len(remaining), rejected))
    return remaining, tuple(steps)


def _facet_scores(case: SelectionCase, component: ComponentDescriptor) -> dict[str, float]:
    source = _ratio(
        len(case.objective.source_functions & component.source_functions),
        len(case.objective.source_functions),
    )
    declared = frozenset(case.projection.declared_presentations)
    presentation = (
        _ratio(len(declared & component.presentations), len(declared)) if declared else 1.0
    )
    affordance = _ratio(
        len(case.desired_affordances & component.affordances),
        len(case.desired_affordances),
    )
    evidence = _ratio(
        len(case.desired_evidence_events & component.evidence_events),
        len(case.desired_evidence_events),
    )
    catalog_rank = 1.0 / (1.0 + component.rank)
    total = (
        FACET_WEIGHTS["source"] * source
        + FACET_WEIGHTS["presentation"] * presentation
        + FACET_WEIGHTS["affordance"] * affordance
        + FACET_WEIGHTS["evidence"] * evidence
        + FACET_WEIGHTS["catalog_rank"] * catalog_rank
    )
    return {
        "source": source,
        "presentation": presentation,
        "affordance": affordance,
        "evidence": evidence,
        "catalog_rank": catalog_rank,
        "total": total,
    }


def _component_tokens(component: ComponentDescriptor) -> tuple[str, ...]:
    values = [
        component.component_id,
        *(value.value for value in component.missions),
        *(value.value for value in component.source_functions),
        *(value.value for value in component.presentations),
        *component.affordances,
        *component.evidence_events,
        *component.requirements,
        component.producer_kind.value,
    ]
    return _tokens(values)


def _tfidf_vectors(
    query: tuple[str, ...], documents: Mapping[str, tuple[str, ...]]
) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    document_count = len(documents)
    frequencies = Counter(token for tokens in documents.values() for token in set(tokens))

    def vector(tokens: tuple[str, ...]) -> dict[str, float]:
        counts = Counter(tokens)
        return {
            token: count * (math.log((1 + document_count) / (1 + frequencies[token])) + 1)
            for token, count in counts.items()
        }

    return vector(query), {key: vector(tokens) for key, tokens in documents.items()}


def _cosine(left: Mapping[str, float], right: Mapping[str, float]) -> float:
    common = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in common)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _rank_candidates(
    strategy: str,
    case: SelectionCase,
    eligible: tuple[ComponentDescriptor, ...],
    top_k: int,
) -> list[dict[str, Any]]:
    if strategy == "eligible-full":
        return [
            {
                "component_id": item.component_id,
                "scores": {"catalog_rank": 1.0 / (1.0 + item.rank)},
            }
            for item in sorted(eligible, key=lambda item: (item.rank, item.component_id))
        ]

    if strategy == "facets-top-k":
        scored = [(item, _facet_scores(case, item)) for item in eligible]
        scored.sort(key=lambda pair: (-pair[1]["total"], pair[0].rank, pair[0].component_id))
        return [
            {"component_id": item.component_id, "scores": scores} for item, scores in scored[:top_k]
        ]

    if strategy != "lexical-diverse-top-k":
        raise ValueError(f"unknown strategy: {strategy}")

    documents = {item.component_id: _component_tokens(item) for item in eligible}
    query = _tokens(case.query_terms)
    query_vector, document_vectors = _tfidf_vectors(query, documents)
    relevance = {
        component_id: _cosine(query_vector, vector)
        for component_id, vector in document_vectors.items()
    }
    remaining = {item.component_id: item for item in eligible}
    selected: list[dict[str, Any]] = []
    selected_tokens: list[frozenset[str]] = []
    while remaining and len(selected) < top_k:
        best: tuple[float, float, int, str, float] | None = None
        for component_id, component in remaining.items():
            tokens = frozenset(documents[component_id])
            max_similarity = max(
                (_jaccard(tokens, previous) for previous in selected_tokens), default=0.0
            )
            novelty = 1.0 - max_similarity
            selection_score = (
                LEXICAL_RELEVANCE_WEIGHT * relevance[component_id]
                + LEXICAL_NOVELTY_WEIGHT * novelty
            )
            candidate = (
                selection_score,
                relevance[component_id],
                -component.rank,
                component_id,
                novelty,
            )
            if (
                best is None
                or candidate[:3] > best[:3]
                or (candidate[:3] == best[:3] and candidate[3] < best[3])
            ):
                best = candidate
        assert best is not None
        selection_score, lexical_score, _, component_id, novelty = best
        selected.append(
            {
                "component_id": component_id,
                "scores": {
                    "lexical": lexical_score,
                    "novelty": novelty,
                    "total": selection_score,
                },
            }
        )
        selected_tokens.append(frozenset(documents[component_id]))
        remaining.pop(component_id)
    return selected


def _retrieval_metrics(
    case: SelectionCase,
    selected_ids: tuple[str, ...],
    descriptors: Mapping[str, ComponentDescriptor],
) -> dict[str, Any]:
    selected = frozenset(selected_ids)
    relevant_hits = selected & case.relevant_components
    forbidden_hits = selected & case.forbidden_components
    affordances = (
        frozenset().union(*(descriptors[item].affordances for item in selected_ids))
        if selected_ids
        else frozenset()
    )
    evidence = (
        frozenset().union(*(descriptors[item].evidence_events for item in selected_ids))
        if selected_ids
        else frozenset()
    )
    return {
        "hit": bool(relevant_hits),
        "relevant_recall": _ratio(len(relevant_hits), len(case.relevant_components)),
        "relevant_precision": _ratio(len(relevant_hits), len(selected)),
        "forbidden_count": len(forbidden_hits),
        "forbidden_components": sorted(forbidden_hits),
        "affordance_coverage": _ratio(
            len(affordances & case.desired_affordances), len(case.desired_affordances)
        ),
        "evidence_coverage": _ratio(
            len(evidence & case.desired_evidence_events),
            len(case.desired_evidence_events),
        ),
    }


def run_manifest(
    raw: Mapping[str, Any],
    *,
    catalog: tuple[ComponentDescriptor, ...] | None = None,
) -> dict[str, Any]:
    top_k, cases = load_manifest(raw)
    component_catalog = catalog or adapt_legacy_openui_catalog()
    descriptors = {item.component_id: item for item in component_catalog}
    results: list[dict[str, Any]] = []

    for case in cases:
        unknown = (case.relevant_components | case.forbidden_components) - descriptors.keys()
        if unknown:
            raise ValueError(
                f"case {case.case_id!r} references unknown components: {sorted(unknown)}"
            )
        eligible, filter_steps = filter_catalog(case, component_catalog)
        for strategy in STRATEGIES:
            started = time.perf_counter_ns()
            shortlist = _rank_candidates(strategy, case, eligible, top_k)
            elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
            selected_ids = tuple(item["component_id"] for item in shortlist)
            results.append(
                {
                    "case_id": case.case_id,
                    "strategy": strategy,
                    "intent_text": case.intent_text,
                    "query_terms": list(case.query_terms),
                    "eligible_count": len(eligible),
                    "filters": [asdict(step) for step in filter_steps],
                    "shortlist": shortlist,
                    "latency_ms": elapsed_ms,
                    "metrics": _retrieval_metrics(case, selected_ids, descriptors),
                }
            )

    summaries: dict[str, dict[str, Any]] = {}
    for strategy in STRATEGIES:
        rows = [row for row in results if row["strategy"] == strategy]
        latencies = [row["latency_ms"] for row in rows]
        summaries[strategy] = {
            "cases": len(rows),
            "hit_rate": statistics.fmean(float(row["metrics"]["hit"]) for row in rows),
            "mean_relevant_recall": statistics.fmean(
                row["metrics"]["relevant_recall"] for row in rows
            ),
            "mean_relevant_precision": statistics.fmean(
                row["metrics"]["relevant_precision"] for row in rows
            ),
            "forbidden_total": sum(row["metrics"]["forbidden_count"] for row in rows),
            "mean_affordance_coverage": statistics.fmean(
                row["metrics"]["affordance_coverage"] for row in rows
            ),
            "mean_evidence_coverage": statistics.fmean(
                row["metrics"]["evidence_coverage"] for row in rows
            ),
            "latency_ms": {
                "mean": statistics.fmean(latencies),
                "p50": statistics.median(latencies),
                "p95": _percentile(latencies, 0.95),
            },
        }

    return {
        "bench_version": BENCH_VERSION,
        "fixture_id": raw.get("fixture_id"),
        "catalog_version": catalog_version(),
        "catalog_size": len(component_catalog),
        "top_k": top_k,
        "strategies": list(STRATEGIES),
        "policy": {
            "facet_weights": FACET_WEIGHTS,
            "lexical_relevance_weight": LEXICAL_RELEVANCE_WEIGHT,
            "lexical_novelty_weight": LEXICAL_NOVELTY_WEIGHT,
        },
        "summaries": summaries,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark offline de selección de componentes")
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = run_manifest(json.loads(args.input.read_text(encoding="utf-8")))
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.out:
        args.out.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
