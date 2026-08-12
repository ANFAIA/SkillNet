"""Reproducible offline experiment for Didact shortlist retrieval.

This is deliberately a bench, not runtime code.  Hard capability gates are applied
before every ranking policy.  The semantic proxy is BM25 because the repository does
not ship a local embedding model whose weights can be reproduced without network I/O.
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
from typing import Any, Mapping, Sequence
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


BENCH_VERSION = "didact-shortlist/1"
RETRIEVAL_BACKEND = "bm25-lexical-proxy/1"
STRATEGIES = (
    "eligible-full",
    "facets-top5",
    "bm25-top5",
    "hybrid-facets-bm25-top5",
    "hybrid-facets-bm25-diverse-top5",
)
BM25_K1 = 1.5
BM25_B = 0.75
HYBRID_FACET_WEIGHT = 0.55
HYBRID_BM25_WEIGHT = 0.45
DIVERSITY_WEIGHT = 0.18
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_STOP_WORDS = frozenset({"a", "an", "and", "component", "for", "of", "the", "to", "with"})


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


@dataclass(frozen=True, slots=True)
class ExperimentCase:
    selection: SelectionCase
    preferred_components: frozenset[str]
    evidence_components: frozenset[str]


def _parse_case(raw: Mapping[str, Any]) -> ExperimentCase:
    objective = raw["objective"]
    projection = raw.get("projection", {})
    case_id = str(raw["id"])
    selection = SelectionCase(
        case_id=case_id,
        intent_text=str(raw["intent_text"]),
        query_terms=tuple(map(str, raw["query_terms"])),
        objective=LearningObjective(
            objective_id=case_id,
            objective_version=1,
            mission=CognitiveMission(objective["mission"]),
            source_functions=frozenset(
                SourceFunction(value) for value in objective["source_functions"]
            ),
            available_requirements=frozenset(
                map(str, objective.get("available_requirements", []))
            ),
        ),
        projection=PersonalizationProjection(
            declared_presentations=tuple(
                Presentation(value) for value in projection.get("presentations", [])
            ),
            accessibility_capabilities=frozenset(
                AccessibilityCapability(value)
                for value in projection.get("accessibility", [])
            ),
        ),
        desired_affordances=frozenset(map(str, raw.get("desired_affordances", []))),
        desired_evidence_events=frozenset(),
        relevant_components=frozenset(map(str, raw["relevant_components"])),
        forbidden_components=frozenset(map(str, raw.get("forbidden_components", []))),
    )
    return ExperimentCase(
        selection=selection,
        preferred_components=frozenset(map(str, raw.get("preferred_components", []))),
        evidence_components=frozenset(map(str, raw.get("evidence_components", []))),
    )


def _tokens(values: Sequence[str]) -> tuple[str, ...]:
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


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = math.ceil(percentile * len(ordered)) - 1
    return ordered[max(0, min(index, len(ordered) - 1))]


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def filter_catalog(
    case: SelectionCase, catalog: tuple[ComponentDescriptor, ...]
) -> tuple[tuple[ComponentDescriptor, ...], tuple[FilterStep, ...]]:
    remaining = catalog
    filters = (
        ("mission", lambda item: case.objective.mission in item.missions),
        ("source_function", lambda item: bool(case.objective.source_functions & item.source_functions)),
        ("requirements", lambda item: item.requirements <= case.objective.available_requirements),
        ("accessibility", lambda item: case.projection.accessibility_capabilities <= item.accessibility),
    )
    steps: list[FilterStep] = []
    for name, predicate in filters:
        before = len(remaining)
        rejected = tuple(item.component_id for item in remaining if not predicate(item))
        remaining = tuple(item for item in remaining if predicate(item))
        steps.append(FilterStep(name, before, len(remaining), rejected))
    return remaining, tuple(steps)


def _ratio(matched: int, desired: int) -> float:
    return matched / desired if desired else 1.0


def _facet_scores(case: SelectionCase, component: ComponentDescriptor) -> dict[str, float]:
    declared = frozenset(case.projection.declared_presentations)
    source = _ratio(
        len(case.objective.source_functions & component.source_functions),
        len(case.objective.source_functions),
    )
    presentation = _ratio(len(declared & component.presentations), len(declared)) if declared else 1.0
    affordance = _ratio(
        len(case.desired_affordances & component.affordances), len(case.desired_affordances)
    )
    total = 0.35 * source + 0.20 * presentation + 0.40 * affordance + 0.05 / (1 + component.rank)
    return {"source": source, "presentation": presentation, "affordance": affordance, "total": total}


def load_fixture(raw: Mapping[str, Any]) -> tuple[int, tuple[ExperimentCase, ...]]:
    if raw.get("version") != BENCH_VERSION:
        raise ValueError(f"fixture version must be {BENCH_VERSION!r}")
    top_k = int(raw.get("top_k", 5))
    if top_k != 5:
        raise ValueError("this experiment fixes top_k at 5")
    cases = tuple(_parse_case(item) for item in raw.get("cases", []))
    if not cases:
        raise ValueError("fixture must contain cases")
    return top_k, cases


def _snapshot_documents(snapshot: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    manifests = {item["id"]: item for item in snapshot["manifests"]}
    documents: dict[str, tuple[str, ...]] = {}
    for item in snapshot["available_types"]:
        manifest = manifests[item["manifest_id"]]
        facets = manifest["facets"]
        values: list[str] = [
            item["id"],
            item["export_name"],
            manifest["name"],
            manifest["description"],
            manifest["role"],
            *manifest["tags"],
            *manifest["families"],
            *manifest["capabilities"],
            *facets["purposes"],
            *facets["learnerActions"],
            *facets["representations"],
            *facets["subjects"],
        ]
        values.extend(field["description"] for field in manifest["authoring"]["fields"])
        values.extend(
            str(value)
            for variant in manifest["variants"]
            for value in (variant.get("name"), variant.get("description"))
            if value
        )
        documents[item["id"]] = _tokens(values)
    return documents


def _bm25(query: tuple[str, ...], documents: Mapping[str, tuple[str, ...]]) -> dict[str, float]:
    count = len(documents)
    average_length = statistics.fmean(len(value) for value in documents.values())
    document_frequency = Counter(token for value in documents.values() for token in set(value))
    scores: dict[str, float] = {}
    for component_id, tokens in documents.items():
        frequencies = Counter(tokens)
        score = 0.0
        for token in query:
            frequency = frequencies[token]
            if not frequency:
                continue
            inverse_frequency = math.log(
                1 + (count - document_frequency[token] + 0.5) / (document_frequency[token] + 0.5)
            )
            denominator = frequency + BM25_K1 * (
                1 - BM25_B + BM25_B * len(tokens) / average_length
            )
            score += inverse_frequency * frequency * (BM25_K1 + 1) / denominator
        scores[component_id] = score
    maximum = max(scores.values(), default=0.0)
    return {key: value / maximum if maximum else 0.0 for key, value in scores.items()}


def _rank(
    strategy: str,
    case: Any,
    eligible: tuple[ComponentDescriptor, ...],
    documents: Mapping[str, tuple[str, ...]],
    top_k: int,
) -> list[dict[str, Any]]:
    if strategy == "eligible-full":
        return [{"component_id": item.component_id, "scores": {}} for item in eligible]
    facet = {item.component_id: _facet_scores(case, item)["total"] for item in eligible}
    lexical = _bm25(_tokens((*case.query_terms, case.intent_text)), {
        item.component_id: documents[item.component_id] for item in eligible
    })
    if strategy == "facets-top5":
        total = facet
    elif strategy == "bm25-top5":
        total = lexical
    elif strategy in {"hybrid-facets-bm25-top5", "hybrid-facets-bm25-diverse-top5"}:
        total = {
            item.component_id: HYBRID_FACET_WEIGHT * facet[item.component_id]
            + HYBRID_BM25_WEIGHT * lexical[item.component_id]
            for item in eligible
        }
    else:
        raise ValueError(f"unknown strategy: {strategy}")

    remaining = {item.component_id: item for item in eligible}
    selected: list[dict[str, Any]] = []
    selected_tokens: list[frozenset[str]] = []
    while remaining and len(selected) < top_k:
        candidates = []
        for component_id, component in remaining.items():
            novelty = 1.0
            if strategy.endswith("diverse-top5"):
                novelty = 1.0 - max(
                    (_jaccard(frozenset(documents[component_id]), previous)
                     for previous in selected_tokens),
                    default=0.0,
                )
            score = total[component_id]
            if strategy.endswith("diverse-top5"):
                score = (1 - DIVERSITY_WEIGHT) * score + DIVERSITY_WEIGHT * novelty
            candidates.append((score, -component.rank, component_id, novelty))
        score, _, component_id, novelty = max(candidates, key=lambda value: (value[0], value[1], value[2]))
        selected.append({
            "component_id": component_id,
            "scores": {
                "facet": facet[component_id],
                "bm25": lexical[component_id],
                "novelty": novelty,
                "total": score,
            },
        })
        selected_tokens.append(frozenset(documents[component_id]))
        remaining.pop(component_id)
    return selected


def _coverage(selected: set[str], desired: frozenset[str]) -> float:
    return len(selected & desired) / len(desired) if desired else 1.0


def _intra_shortlist_diversity(
    selected_ids: list[str], documents: Mapping[str, tuple[str, ...]]
) -> float:
    pairs = [
        1.0 - _jaccard(frozenset(documents[left]), frozenset(documents[right]))
        for index, left in enumerate(selected_ids)
        for right in selected_ids[index + 1 :]
    ]
    return statistics.fmean(pairs) if pairs else 0.0


def run_experiment(raw: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    top_k, cases = load_fixture(raw)
    catalog = export_didact_descriptors()
    descriptors = {item.component_id: item for item in catalog}
    documents = _snapshot_documents(snapshot)
    results: list[dict[str, Any]] = []
    for experiment_case in cases:
        case = experiment_case.selection
        referenced = (
            case.relevant_components
            | case.forbidden_components
            | experiment_case.preferred_components
            | experiment_case.evidence_components
        )
        if unknown := referenced - descriptors.keys():
            raise ValueError(f"case {case.case_id} has unknown components: {sorted(unknown)}")
        eligible, filters = filter_catalog(case, catalog)
        for strategy in STRATEGIES:
            started = time.perf_counter_ns()
            shortlist = _rank(strategy, case, eligible, documents, top_k)
            elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
            selected_ids = [item["component_id"] for item in shortlist]
            selected = set(selected_ids)
            actions = set().union(*(descriptors[item].affordances for item in selected_ids))
            results.append({
                "case_id": case.case_id,
                "strategy": strategy,
                "eligible_count": len(eligible),
                "filters": [asdict(item) for item in filters],
                "shortlist": shortlist,
                "latency_ms": elapsed_ms,
                "metrics": {
                    "relevant_recall": _coverage(selected, case.relevant_components),
                    "evidence_coverage": _coverage(selected, experiment_case.evidence_components),
                    "affordance_coverage": _coverage(actions, case.desired_affordances),
                    "preference_coverage": _coverage(selected, experiment_case.preferred_components),
                    "forbidden_count": len(selected & case.forbidden_components),
                    "intra_shortlist_diversity": _intra_shortlist_diversity(
                        selected_ids, documents
                    ),
                },
            })

    summaries: dict[str, Any] = {}
    for strategy in STRATEGIES:
        rows = [item for item in results if item["strategy"] == strategy]
        selected = [entry["component_id"] for row in rows for entry in row["shortlist"]]
        unique = len(set(selected))
        denominator = min(len(catalog), sum(len(row["shortlist"]) for row in rows))
        latency = [row["latency_ms"] for row in rows]
        summaries[strategy] = {
            "cases": len(rows),
            "mean_shortlist_size": statistics.fmean(len(row["shortlist"]) for row in rows),
            "mean_relevant_recall": statistics.fmean(row["metrics"]["relevant_recall"] for row in rows),
            "mean_evidence_coverage": statistics.fmean(row["metrics"]["evidence_coverage"] for row in rows),
            "mean_affordance_coverage": statistics.fmean(row["metrics"]["affordance_coverage"] for row in rows),
            "mean_preference_coverage": statistics.fmean(row["metrics"]["preference_coverage"] for row in rows),
            "forbidden_total": sum(row["metrics"]["forbidden_count"] for row in rows),
            "unique_components": unique,
            "catalog_variety": unique / denominator if denominator else 0.0,
            "mean_intra_shortlist_diversity": statistics.fmean(
                row["metrics"]["intra_shortlist_diversity"] for row in rows
            ),
            "latency_ms": {
                "mean": statistics.fmean(latency),
                "p50": statistics.median(latency),
                "p95": _percentile(latency, 0.95),
            },
        }
    return {
        "bench_version": BENCH_VERSION,
        "fixture_id": raw.get("fixture_id"),
        "retrieval_backend": RETRIEVAL_BACKEND,
        "embedding_backend": None,
        "embedding_reason": "No versioned local embedding weights are shipped by this repository; network-dependent providers are excluded from a reproducible offline bench.",
        "catalog_size": len(catalog),
        "top_k": top_k,
        "strategies": list(STRATEGIES),
        "configuration": {
            "bm25_k1": BM25_K1,
            "bm25_b": BM25_B,
            "hybrid_facet_weight": HYBRID_FACET_WEIGHT,
            "hybrid_bm25_weight": HYBRID_BM25_WEIGHT,
            "diversity_weight": DIVERSITY_WEIGHT,
            "hard_gates": ["mission", "source_function", "requirements", "accessibility"],
        },
        "summaries": summaries,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--snapshot", type=Path, default=Path("src/personalization/didact_snapshot.json"))
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = run_experiment(
        json.loads(args.fixture.read_text(encoding="utf-8")),
        json.loads(args.snapshot.read_text(encoding="utf-8")),
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.out:
        args.out.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
