#!/usr/bin/env python
"""Offline experiment: progressive access to all 34 Didact components.

The harness compares the current fixed top-5 shortlist with a progressive strategy:
top 3 -> top 5 -> full inventory plus a producer-specialist pass.  It is deliberately
isolated from runtime production code and uses a deterministic fixture proxy, not an LLM.

Hard gates only reject definitions that cannot be grounded in the supplied facts or
whose required authoring data cannot be produced.  Richness is a reason to *expand* the
search, never a reason to hide a component from the creative search space.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:  # package import under pytest
    from scripts.rich_generation_bench import Component, load_components
except ModuleNotFoundError:  # direct `python scripts/...` execution
    from rich_generation_bench import Component, load_components


BENCH_VERSION = "didact-progressive-selection/1"
DEFAULT_FIXTURE = Path(__file__).parents[1] / "tests/fixtures/rich-generation-v1.json"
ARMS = ("fixed-top5", "progressive-34")
RICHNESS_THRESHOLD = 0.92


@dataclass(frozen=True)
class Selection:
    components: tuple[Component, ...]
    stage: str
    considered: tuple[str, ...]
    context_units: int
    operation_units: int
    hard_gate_failures: int = 0


def _ratio(hit: int, wanted: int) -> float:
    return hit / wanted if wanted else 1.0


def _component_score(
    component: Component, scenario: dict[str, Any], profile: dict[str, Any]
) -> float:
    wanted_actions = set(scenario["actions"])
    wanted_reps = set(scenario["representations"])
    wanted_purposes = set(scenario["purposes"])
    wanted_evidence = set(scenario["evidence"])
    preferred = set(profile["preferred_representations"])
    return (
        0.28 * _ratio(len(wanted_actions & component.actions), len(wanted_actions))
        + 0.18 * _ratio(len(wanted_reps & component.representations), len(wanted_reps))
        + 0.14 * _ratio(len(wanted_purposes & component.purposes), len(wanted_purposes))
        + 0.22 * _ratio(len(wanted_evidence & component.evidence), len(wanted_evidence))
        + 0.18 * _ratio(len(preferred & component.representations), len(preferred))
    )


def _rank(
    inventory: tuple[Component, ...], scenario: dict[str, Any], profile: dict[str, Any]
) -> list[Component]:
    return sorted(
        inventory,
        key=lambda component: (-_component_score(component, scenario, profile), component.id),
    )


def _coverage(
    selected: Iterable[Component], scenario: dict[str, Any], profile: dict[str, Any]
) -> dict[str, float]:
    values = tuple(selected)
    actions = set().union(*(item.actions for item in values))
    reps = set().union(*(item.representations for item in values))
    evidence = set().union(*(item.evidence for item in values))
    preferred = set(profile["preferred_representations"])
    return {
        "affordance": _ratio(len(actions & set(scenario["actions"])), len(scenario["actions"])),
        "evidence": _ratio(len(evidence & set(scenario["evidence"])), len(scenario["evidence"])),
        "theme": _ratio(len(reps & set(scenario["representations"])), len(scenario["representations"])),
        "preference": _ratio(len(reps & preferred), len(preferred)),
    }


def _richness(
    selected: Iterable[Component], scenario: dict[str, Any], profile: dict[str, Any]
) -> float:
    coverage = _coverage(selected, scenario, profile)
    return (
        0.34 * coverage["affordance"]
        + 0.28 * coverage["evidence"]
        + 0.23 * coverage["theme"]
        + 0.15 * coverage["preference"]
    )


def _compose(candidates: Iterable[Component], scenario: dict[str, Any], profile: dict[str, Any]) -> tuple[Component, ...]:
    """Choose at most two components; a second must add a missing learning channel."""
    ranked = tuple(candidates)
    if not ranked:
        return ()
    chosen = [ranked[0]]
    baseline = _richness(chosen, scenario, profile)
    complements = sorted(
        (
            (_richness((*chosen, candidate), scenario, profile) - baseline, candidate)
            for candidate in ranked[1:]
        ),
        key=lambda item: (-item[0], item[1].id),
    )
    if complements and complements[0][0] >= 0.08:
        chosen.append(complements[0][1])
    return tuple(chosen)


def _definition_is_buildable(component: Component, scenario: dict[str, Any]) -> bool:
    """The only authoring hard gate: required fields need grounded source material."""
    facts = tuple(scenario.get("source_facts", ()))
    if not facts:
        return not component.required_fields
    # Required scalar/list shells can be derived from grounded facts. Components are not
    # rejected for being complex or lacking a production adapter in today's runtime.
    return len(facts) >= min(2, len(component.required_fields))


def _safe_candidates(candidates: Iterable[Component], scenario: dict[str, Any]) -> tuple[tuple[Component, ...], int]:
    valid: list[Component] = []
    failures = 0
    for candidate in candidates:
        if _definition_is_buildable(candidate, scenario):
            valid.append(candidate)
        else:
            failures += 1
    return tuple(valid), failures


def _fixed(ranked: list[Component], scenario: dict[str, Any], profile: dict[str, Any]) -> Selection:
    candidates, failures = _safe_candidates(ranked[:5], scenario)
    selected = _compose(candidates, scenario, profile)
    return Selection(selected, "top5", tuple(item.id for item in ranked[:5]), 5, 5, failures)


def _progressive(ranked: list[Component], scenario: dict[str, Any], profile: dict[str, Any]) -> Selection:
    top3, failures = _safe_candidates(ranked[:3], scenario)
    selected = _compose(top3, scenario, profile)
    if selected and _richness(selected, scenario, profile) >= RICHNESS_THRESHOLD:
        return Selection(selected, "top3", tuple(item.id for item in ranked[:3]), 3, 3, failures)

    top5, new_failures = _safe_candidates(ranked[:5], scenario)
    failures += new_failures
    selected = _compose(top5, scenario, profile)
    if selected and _richness(selected, scenario, profile) >= RICHNESS_THRESHOLD:
        return Selection(selected, "top5", tuple(item.id for item in ranked[:5]), 8, 8, failures)

    # The specialist receives the compact intent plus descriptor facets for every type,
    # then searches globally for the best complementary producer. All 34 are genuinely
    # considered here; no renderer/emittable gate narrows the creative choice.
    full, new_failures = _safe_candidates(ranked, scenario)
    failures += new_failures
    selected = _compose(full, scenario, profile)
    return Selection(
        selected,
        "producer-full34",
        tuple(item.id for item in ranked),
        8 + len(ranked),
        8 + len(ranked) * 2,
        failures,
    )


def _entropy(signatures: Iterable[tuple[str, ...]]) -> float:
    counts = Counter(signatures)
    total = sum(counts.values())
    return -sum((count / total) * math.log2(count / total) for count in counts.values()) if total else 0.0


def run_manifest(raw: dict[str, Any], inventory: tuple[Component, ...] | None = None) -> dict[str, Any]:
    if raw.get("version") != "rich-generation/1":
        raise ValueError("fixture version must be rich-generation/1")
    components = inventory or load_components()
    if len(components) != 34:
        raise ValueError(f"expected the complete 34-component inventory, got {len(components)}")
    rows: list[dict[str, Any]] = []
    for scenario in raw["scenarios"]:
        for profile in raw["profiles"]:
            ranked = _rank(components, scenario, profile)
            for seed in raw["seeds"]:
                # Seeds repeat the same deterministic decision to keep comparison paired;
                # future real-model runs can use them as provider seeds.
                for arm in ARMS:
                    selection = (
                        _fixed(ranked, scenario, profile)
                        if arm == "fixed-top5"
                        else _progressive(ranked, scenario, profile)
                    )
                    coverage = _coverage(selection.components, scenario, profile)
                    quality = 100 * _richness(selection.components, scenario, profile)
                    selected_ids = tuple(item.id for item in selection.components)
                    rows.append(
                        {
                            "scenario": scenario["id"],
                            "profile": profile["id"],
                            "seed": seed,
                            "arm": arm,
                            "stage": selection.stage,
                            "selected": list(selected_ids),
                            "considered_count": len(selection.considered),
                            "all_34_considered": len(selection.considered) == 34,
                            "metrics": {
                                "quality_proxy": round(quality, 2),
                                "preference_fit": round(coverage["preference"], 3),
                                "affordance_coverage": round(coverage["affordance"], 3),
                                "evidence_coverage": round(coverage["evidence"], 3),
                                "theme_fit": round(coverage["theme"], 3),
                            },
                            "expanded": arm == "progressive-34" and selection.stage != "top3",
                            "fallback": selection.stage == "producer-full34",
                            "hard_gate_failures": selection.hard_gate_failures,
                            "context_units": selection.context_units,
                            "latency_proxy_units": selection.operation_units,
                        }
                    )

    summaries: dict[str, Any] = {}
    for arm in ARMS:
        arm_rows = [row for row in rows if row["arm"] == arm]
        selected_types = {value for row in arm_rows for value in row["selected"]}
        signatures = [tuple(row["selected"]) for row in arm_rows]
        stages = Counter(row["stage"] for row in arm_rows)
        summaries[arm] = {
            "runs": len(arm_rows),
            "mean_quality_proxy": round(statistics.fmean(row["metrics"]["quality_proxy"] for row in arm_rows), 3),
            "mean_preference_fit": round(statistics.fmean(row["metrics"]["preference_fit"] for row in arm_rows), 3),
            "mean_affordance_coverage": round(statistics.fmean(row["metrics"]["affordance_coverage"] for row in arm_rows), 3),
            "mean_evidence_coverage": round(statistics.fmean(row["metrics"]["evidence_coverage"] for row in arm_rows), 3),
            "mean_theme_fit": round(statistics.fmean(row["metrics"]["theme_fit"] for row in arm_rows), 3),
            "distinct_selected_types": len(selected_types),
            "selection_entropy_bits": round(_entropy(signatures), 3),
            "expansion_rate": round(statistics.fmean(float(row["expanded"]) for row in arm_rows), 3),
            "fallback_rate": round(statistics.fmean(float(row["fallback"]) for row in arm_rows), 3),
            "full_catalog_activation_rate": round(statistics.fmean(float(row["all_34_considered"]) for row in arm_rows), 3),
            "mean_context_units": round(statistics.fmean(row["context_units"] for row in arm_rows), 3),
            "mean_latency_proxy_units": round(statistics.fmean(row["latency_proxy_units"] for row in arm_rows), 3),
            "hard_gate_failures": sum(row["hard_gate_failures"] for row in arm_rows),
            "stage_counts": dict(sorted(stages.items())),
        }
    return {
        "bench_version": BENCH_VERSION,
        "claim_boundary": "deterministic fixture proxy; not real-LLM latency or quality evidence",
        "inventory_size": len(components),
        "richness_threshold": RICHNESS_THRESHOLD,
        "scenario_count": len(raw["scenarios"]),
        "profile_count": len(raw["profiles"]),
        "seed_count": len(raw["seeds"]),
        "summaries": summaries,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = run_manifest(json.loads(args.input.read_text(encoding="utf-8")))
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
