"""Offline ceiling test for an experience-first component-selection boundary.

This benchmark compares two adapters into the *same* deterministic Didact selector:

``direct``
    Objective/profile prose is reduced by exact controlled-vocabulary matches.
``experience-intent``
    A typed, component-agnostic educational intent is supplied before selection.

The typed fixture is deliberately an oracle, not an NLP implementation.  The experiment
therefore asks whether the boundary is worth building, not whether a parser is good yet.
No LLM, embedding service, database or live runtime is used.
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

from src.personalization.didact_catalog import (  # noqa: E402
    DidactComponentAvailability,
    load_didact_catalog,
)


BENCH_VERSION = "experience-intent/1"
STRATEGIES = ("direct", "experience-intent")
WEIGHTS = {
    "actions": 0.30,
    "evidence": 0.25,
    "feedback": 0.20,
    "representations": 0.15,
    "depth": 0.10,
}
_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class ExperienceIntent:
    actions: frozenset[str]
    evidence: frozenset[str]
    feedback: frozenset[str]
    representations: frozenset[str]
    depth: int

    def __post_init__(self) -> None:
        if not 1 <= self.depth <= 4:
            raise ValueError("intent depth must be between 1 and 4")


@dataclass(frozen=True, slots=True)
class Case:
    case_id: str
    pair_id: str | None
    objective_text: str
    profile_text: str
    available_ports: frozenset[str]
    required_accessibility: frozenset[str]
    typed_intent: ExperienceIntent
    expected_outcome: str


@dataclass(frozen=True, slots=True)
class Candidate:
    component_id: str
    actions: frozenset[str]
    evidence: frozenset[str]
    feedback: frozenset[str]
    representations: frozenset[str]
    depth: int
    requirements: frozenset[str]
    accessibility: frozenset[str]


def _tokens(text: str) -> frozenset[str]:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return frozenset(_TOKEN_RE.findall(normalized.lower()))


def _capabilities(component: DidactComponentAvailability, prefix: str) -> frozenset[str]:
    return frozenset(value for value in component.capabilities if value.startswith(prefix))


def _depth(component: DidactComponentAvailability) -> int:
    purposes = set(component.purposes)
    if purposes & {"create", "simulate"}:
        return 4
    if purposes & {"practice", "assess", "explore"}:
        return 3
    if purposes & {"scaffold", "reflect", "retrieve"}:
        return 2
    return 1


def build_candidates() -> tuple[Candidate, ...]:
    return tuple(
        Candidate(
            component_id=item.type_id,
            actions=frozenset(item.learner_actions),
            evidence=_capabilities(item, "response:") | _capabilities(item, "result:"),
            feedback=_capabilities(item, "feedback:"),
            representations=frozenset(item.representations),
            depth=_depth(item),
            requirements=frozenset(port.value for port in item.required_ports),
            accessibility=frozenset(
                name
                for name, state in (
                    ("keyboard", item.keyboard_access),
                    ("screen_reader", item.screen_reader_access),
                )
                if state == "full"
            ),
        )
        for item in load_didact_catalog().components
    )


def _parse_intent(raw: Mapping[str, Any]) -> ExperienceIntent:
    return ExperienceIntent(
        actions=frozenset(map(str, raw.get("actions", []))),
        evidence=frozenset(map(str, raw.get("evidence", []))),
        feedback=frozenset(map(str, raw.get("feedback", []))),
        representations=frozenset(map(str, raw.get("representations", []))),
        depth=int(raw["depth"]),
    )


def load_manifest(raw: Mapping[str, Any]) -> tuple[int, tuple[Case, ...]]:
    if raw.get("version") != BENCH_VERSION:
        raise ValueError(f"fixture version must be {BENCH_VERSION!r}")
    top_k = int(raw.get("top_k", 3))
    if top_k < 1:
        raise ValueError("top_k must be positive")
    cases = tuple(
        Case(
            case_id=str(item["id"]),
            pair_id=str(item["pair_id"]) if item.get("pair_id") else None,
            objective_text=str(item["objective_text"]),
            profile_text=str(item["profile_text"]),
            available_ports=frozenset(map(str, item.get("available_ports", []))),
            required_accessibility=frozenset(
                map(str, item.get("required_accessibility", []))
            ),
            typed_intent=_parse_intent(item["experience_intent"]),
            expected_outcome=str(item.get("expected_outcome", "produce")),
        )
        for item in raw.get("cases", [])
    )
    if not cases or len({item.case_id for item in cases}) != len(cases):
        raise ValueError("fixture needs cases with unique ids")
    return top_k, cases


def _direct_intent(case: Case, candidates: Sequence[Candidate]) -> ExperienceIntent:
    """Lossy but deterministic vocabulary projection of raw prose.

    Multi-word educational interpretation is intentionally absent. This mirrors the
    failure mode under test: asking catalogue retrieval to infer pedagogy from prose.
    """

    tokens = _tokens(f"{case.objective_text} {case.profile_text}")
    actions = frozenset().union(*(item.actions for item in candidates))
    evidence = frozenset().union(*(item.evidence for item in candidates))
    feedback = frozenset().union(*(item.feedback for item in candidates))
    representations = frozenset().union(*(item.representations for item in candidates))

    def exact(values: Iterable[str]) -> frozenset[str]:
        return frozenset(value for value in values if _tokens(value) <= tokens)

    depth = 2
    if tokens & {"beginner", "novice", "introductory"}:
        depth = 1
    elif tokens & {"guided", "support", "scaffolded"}:
        depth = 2
    elif tokens & {"independent", "experienced", "practice"}:
        depth = 3
    elif tokens & {"advanced", "expert", "create", "simulate"}:
        depth = 4
    return ExperienceIntent(
        actions=exact(actions),
        evidence=exact(evidence),
        feedback=exact(feedback),
        representations=exact(representations),
        depth=depth,
    )


def _coverage(desired: frozenset[str], delivered: frozenset[str]) -> float:
    return len(desired & delivered) / len(desired) if desired else 1.0


def _candidate_score(intent: ExperienceIntent, candidate: Candidate) -> float:
    return sum(
        (
            WEIGHTS["actions"] * _coverage(intent.actions, candidate.actions),
            WEIGHTS["evidence"] * _coverage(intent.evidence, candidate.evidence),
            WEIGHTS["feedback"] * _coverage(intent.feedback, candidate.feedback),
            WEIGHTS["representations"]
            * _coverage(intent.representations, candidate.representations),
            WEIGHTS["depth"] * (1 - abs(intent.depth - candidate.depth) / 3),
        )
    )


def select(
    intent: ExperienceIntent,
    case: Case,
    candidates: Sequence[Candidate],
    top_k: int,
) -> tuple[Candidate, ...]:
    eligible = tuple(
        item
        for item in candidates
        if item.requirements <= case.available_ports
        and case.required_accessibility <= item.accessibility
    )
    ranked = sorted(
        eligible,
        key=lambda item: (-_candidate_score(intent, item), item.component_id),
    )
    return tuple(ranked[:top_k])


def _union(selected: Sequence[Candidate], field: str) -> frozenset[str]:
    if not selected:
        return frozenset()
    return frozenset().union(*(getattr(item, field) for item in selected))


def _intent_dict(intent: ExperienceIntent) -> dict[str, Any]:
    return {
        "actions": sorted(intent.actions),
        "evidence": sorted(intent.evidence),
        "feedback": sorted(intent.feedback),
        "representations": sorted(intent.representations),
        "depth": intent.depth,
    }


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * percentile) - 1))
    return ordered[index] if ordered else 0.0


def _entropy(signatures: Sequence[tuple[Any, ...]]) -> float:
    if not signatures:
        return 0.0
    counts = Counter(signatures)
    return -sum(
        (count / len(signatures)) * math.log2(count / len(signatures))
        for count in counts.values()
    )


def run_manifest(raw: Mapping[str, Any], *, iterations: int = 200) -> dict[str, Any]:
    top_k, cases = load_manifest(raw)
    candidates = build_candidates()
    rows: list[dict[str, Any]] = []
    for case in cases:
        for strategy in STRATEGIES:
            intent = _direct_intent(case, candidates) if strategy == "direct" else case.typed_intent
            latencies: list[float] = []
            selected: tuple[Candidate, ...] = ()
            for _ in range(iterations):
                started = time.perf_counter_ns()
                selected = select(intent, case, candidates, top_k)
                latencies.append((time.perf_counter_ns() - started) / 1_000_000)
            declined = not selected
            delivered = {
                field: _union(selected, field)
                for field in ("actions", "evidence", "feedback", "representations")
            }
            coverages = {
                field: _coverage(getattr(case.typed_intent, field), values)
                for field, values in delivered.items()
            }
            quality = statistics.fmean(coverages.values()) if not declined else 0.0
            signature = (
                tuple(sorted(delivered["actions"])),
                tuple(sorted(delivered["evidence"])),
                tuple(sorted(delivered["feedback"])),
                tuple(sorted(delivered["representations"])),
                round(statistics.fmean(item.depth for item in selected)) if selected else 0,
            )
            rows.append(
                {
                    "case_id": case.case_id,
                    "pair_id": case.pair_id,
                    "strategy": strategy,
                    "intent": _intent_dict(intent),
                    "selected": [item.component_id for item in selected],
                    "declined": declined,
                    "decline_correct": declined == (case.expected_outcome == "decline"),
                    "coverage": coverages,
                    "quality": quality,
                    "semantic_signature": signature,
                    "latency_ms": {
                        "p50": statistics.median(latencies),
                        "p95": _percentile(latencies, 0.95),
                    },
                }
            )

    pair_metrics: dict[str, list[dict[str, Any]]] = {strategy: [] for strategy in STRATEGIES}
    pair_ids = sorted({case.pair_id for case in cases if case.pair_id})
    for strategy in STRATEGIES:
        for pair_id in pair_ids:
            pair = [
                row
                for row in rows
                if row["strategy"] == strategy and row["pair_id"] == pair_id
            ]
            if len(pair) != 2:
                raise ValueError(f"pair {pair_id!r} must contain exactly two cases")
            left, right = pair
            left_ids, right_ids = set(left["selected"]), set(right["selected"])
            union = left_ids | right_ids
            pair_metrics[strategy].append(
                {
                    "pair_id": pair_id,
                    "semantic_changed": left["semantic_signature"] != right["semantic_signature"],
                    "selection_distance": (
                        1 - len(left_ids & right_ids) / len(union) if union else 0.0
                    ),
                }
            )

    summaries: dict[str, Any] = {}
    for strategy in STRATEGIES:
        strategy_rows = [row for row in rows if row["strategy"] == strategy]
        produced = [row for row in strategy_rows if not row["declined"]]
        useful = [row for row in produced if row["quality"] >= 0.75]
        signatures = [tuple(map(str, row["semantic_signature"])) for row in useful]
        pairs = pair_metrics[strategy]
        summaries[strategy] = {
            "mean_quality": statistics.fmean(row["quality"] for row in strategy_rows),
            "mean_action_coverage": statistics.fmean(
                row["coverage"]["actions"] for row in strategy_rows
            ),
            "mean_evidence_coverage": statistics.fmean(
                row["coverage"]["evidence"] for row in strategy_rows
            ),
            "mean_feedback_coverage": statistics.fmean(
                row["coverage"]["feedback"] for row in strategy_rows
            ),
            "mean_representation_coverage": statistics.fmean(
                row["coverage"]["representations"] for row in strategy_rows
            ),
            "decline_accuracy": statistics.fmean(
                float(row["decline_correct"]) for row in strategy_rows
            ),
            "causal_pair_change_rate": statistics.fmean(
                float(pair["semantic_changed"]) for pair in pairs
            ),
            "mean_pair_selection_distance": statistics.fmean(
                pair["selection_distance"] for pair in pairs
            ),
            "useful_semantic_signatures": len(set(signatures)),
            "useful_semantic_entropy_bits": _entropy(signatures),
            "latency_ms": {
                "p50": statistics.median(row["latency_ms"]["p50"] for row in strategy_rows),
                "p95": _percentile([row["latency_ms"]["p95"] for row in strategy_rows], 0.95),
            },
        }
    return {
        "bench_version": BENCH_VERSION,
        "fixture_id": raw.get("fixture_id"),
        "catalog_size": len(candidates),
        "top_k": top_k,
        "iterations": iterations,
        "weights": WEIGHTS,
        "summaries": summaries,
        "pair_metrics": pair_metrics,
        "results": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline ExperienceIntent ceiling test")
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--iterations", type=int, default=200)
    args = parser.parse_args()
    report = run_manifest(
        json.loads(args.input.read_text(encoding="utf-8")), iterations=args.iterations
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.out:
        args.out.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
