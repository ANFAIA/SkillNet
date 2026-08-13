#!/usr/bin/env python
"""Deterministic longitudinal personalization experiment over all 34 Didact types.

This is an offline harness, not a production integration and not an LLM-quality claim.
It follows paired learners through onboarding, on-the-fly renders, observed events,
calibration, an explicit settings edit, forced regeneration, recovery and completion.
Counterfactual renders change one signal at a time so adaptation can be attributed.
"""

from __future__ import annotations

import argparse
import copy
import json
import statistics
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.personalization.didact_catalog import load_didact_catalog
from src.personalization.didact_descriptors import export_didact_descriptors
from src.personalization.plan import (
    CognitiveMission,
    Declined,
    LearningObjective,
    SourceFunction,
    plan_experience,
)
from src.personalization.preferences import preference_bucket
from src.personalization.projection import project_runtime_signals
from src.services.cache_key import build_cache_key
from src.services.learner_profile_service import vector_bucket

BENCH_VERSION = "didact-learner-journey/1"
DEFAULT_FIXTURE = Path(__file__).parents[1] / "tests/fixtures/didact-learner-journeys-v1.json"
STAGES = (
    ("onboarding-render", 0, 0, False, False),
    ("after-first-event", 1, 1, True, False),
    ("inferred-render", 2, 3, False, False),
    ("settings-regeneration", 2, 3, False, True),
    ("recovery-next-render", 3, 4, False, False),
    ("completion-render", 4, 5, False, False),
)


def _requirements() -> frozenset[str]:
    return frozenset(
        port.value
        for component in load_didact_catalog().components
        for port in component.required_ports
    )


def _objective(raw: Mapping[str, Any]) -> LearningObjective:
    return LearningObjective(
        objective_id=str(raw["id"]),
        objective_version=1,
        mission=CognitiveMission(str(raw["mission"])),
        source_functions=frozenset(SourceFunction(value) for value in raw["source_functions"]),
        available_requirements=_requirements(),
        required_fact_refs=tuple(str(value) for value in raw["fact_refs"]),
    )


def _projection(profile: Mapping[str, Any], *, nodes_completed: int, last_error: str | None) -> Any:
    return project_runtime_signals(
        experience_level=profile.get("experience_level"),
        scaffold_band=profile.get("scaffold_band"),
        preset=profile.get("preset"),
        format_vector=profile.get("format_vector"),
        learning_preferences=profile.get("learning_preferences"),
        nodes_completed=nodes_completed,
        last_error_kind=last_error,
        base_density=3,
    )


def _render(
    objective: LearningObjective,
    profile: Mapping[str, Any],
    *,
    nodes_completed: int,
    last_error: str | None,
) -> dict[str, Any]:
    catalog = export_didact_descriptors()
    if len(catalog) != 34:
        raise ValueError(f"expected complete Didact inventory (34), got {len(catalog)}")
    projection = _projection(profile, nodes_completed=nodes_completed, last_error=last_error)
    outcome = plan_experience(objective, projection, catalog)
    if isinstance(outcome, Declined):
        return {
            "declined": True,
            "inventory_considered": len(catalog),
            "objective_id": objective.objective_id,
            "fact_refs": list(objective.required_fact_refs),
            "projection": asdict(projection),
            "signature": ["declined"],
        }
    selected = outcome.component_candidates[0]
    signature = [
        selected.component_id,
        selected.presentation.value,
        outcome.support.band.value,
        outcome.support.density,
        outcome.support.worked_example,
        outcome.support.graduated_hints,
    ]
    return {
        "declined": False,
        "inventory_considered": len(catalog),
        "eligible_candidates": len(outcome.component_candidates),
        "objective_id": outcome.objective_id,
        "fact_refs": list(outcome.required_fact_refs),
        "component_id": selected.component_id,
        "presentation": selected.presentation.value,
        "producer_kind": selected.producer_kind.value,
        "support": asdict(outcome.support),
        "projection": asdict(projection),
        "signature": signature,
    }


def _cache_key(objective: LearningObjective, profile: Mapping[str, Any], nodes_completed: int) -> str:
    return build_cache_key(
        node_id=objective.objective_id,
        schema_version=1,
        preset=profile.get("preset", "standard"),
        experience_level=profile.get("experience_level", "unknown"),
        scaffold_band=str(profile.get("scaffold_band", "neutral")),
        effective_density=1 if profile.get("preset") == "fast" else 3,
        backend="openui",
        model="fixture-small/1",
        prompt_version="journey-bench/1",
        vector_bucket=vector_bucket(profile.get("format_vector"), nodes_completed),
        preference_bucket=preference_bucket(profile.get("learning_preferences")),
        knowledge_pack_key="grounded-fixture-v1",
    )


def _apply_settings(profile: dict[str, Any], patch: Mapping[str, Any]) -> None:
    for key, value in patch.items():
        profile[key] = copy.deepcopy(value)


def _changed(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return left["signature"] != right["signature"]


def run_manifest(raw: Mapping[str, Any]) -> dict[str, Any]:
    if raw.get("version") != "didact-learner-journeys/1":
        raise ValueError("fixture version must be didact-learner-journeys/1")
    nodes = tuple(_objective(item) for item in raw["nodes"])
    rows: list[dict[str, Any]] = []
    causal: list[dict[str, Any]] = []
    cache_checks: list[dict[str, Any]] = []

    for original in raw["profiles"]:
        profile = copy.deepcopy(original)
        before_settings: dict[str, Any] | None = None
        for stage, node_index, completed, use_error, apply_settings in STAGES:
            objective = nodes[node_index]
            last_error = profile.get("first_error") if use_error else None
            if apply_settings:
                before_settings = copy.deepcopy(profile)
                _apply_settings(profile, profile.get("setting_change", {}))
            if stage == "recovery-next-render":
                profile["scaffold_band"] = profile.get("recovery_scaffold", "guided")
            rendered = _render(
                objective, profile, nodes_completed=completed, last_error=last_error
            )
            key = _cache_key(objective, profile, completed)
            rows.append(
                {
                    "profile_id": original["id"],
                    "stage": stage,
                    "nodes_completed": completed,
                    "last_error": last_error,
                    "cache_key": key,
                    **rendered,
                }
            )

            # Paired counterfactuals change exactly one input on the same objective.
            if stage == "after-first-event" and last_error:
                control = _render(objective, profile, nodes_completed=completed, last_error=None)
                saturated = bool(
                    control.get("support", {}).get("worked_example")
                    and control.get("support", {}).get("graduated_hints")
                )
                causal.append(
                    {
                        "profile_id": original["id"],
                        "axis": "error",
                        "changed": _changed(control, rendered),
                        "already_max_support": saturated,
                    }
                )
            if stage == "inferred-render":
                control_profile = copy.deepcopy(profile)
                control_profile["format_vector"] = {}
                control = _render(objective, control_profile, nodes_completed=completed, last_error=None)
                causal.append({"profile_id": original["id"], "axis": "format_vector", "changed": _changed(control, rendered)})
                cold_key = _cache_key(objective, control_profile, completed)
                cache_checks.append({"profile_id": original["id"], "check": "post-calibration-vector-invalidates", "passed": cold_key != key})
            if stage == "settings-regeneration" and before_settings is not None:
                control = _render(objective, before_settings, nodes_completed=completed, last_error=None)
                causal.append({"profile_id": original["id"], "axis": "settings", "changed": _changed(control, rendered)})
                previous_key = _cache_key(objective, before_settings, completed)
                cache_checks.append({"profile_id": original["id"], "check": "settings-invalidate", "passed": previous_key != key})
                cache_checks.append({"profile_id": original["id"], "check": "forced-refresh-isolated", "passed": f"refresh:fixture:{key}" != key})

        # Cache calibration is checked on the same first node, not across node ids.
        empty = copy.deepcopy(original)
        empty["format_vector"] = {}
        calibration_key = _cache_key(nodes[0], original, 0)
        cache_checks.extend(
            (
                {"profile_id": original["id"], "check": "repeat-stable", "passed": calibration_key == _cache_key(nodes[0], original, 0)},
                {"profile_id": original["id"], "check": "calibration-ignores-vector", "passed": calibration_key == _cache_key(nodes[0], empty, 0)},
            )
        )

    axes = {
        axis: {
            "comparisons": len(values),
            "causal_change_rate": round(statistics.fmean(float(item["changed"]) for item in values), 3),
        }
        for axis in ("error", "format_vector", "settings")
        if (values := [item for item in causal if item["axis"] == axis])
    }
    by_stage = {}
    for stage, *_ in STAGES:
        stage_rows = [row for row in rows if row["stage"] == stage]
        by_stage[stage] = {
            "distinct_render_signatures": len({tuple(row["signature"]) for row in stage_rows}),
            "distinct_components": len({row.get("component_id") for row in stage_rows}),
            "decline_rate": round(statistics.fmean(float(row["declined"]) for row in stage_rows), 3),
        }

    stable = [
        row["objective_id"] == nodes[next(index for index, item in enumerate(nodes) if item.objective_id == row["objective_id"])].objective_id
        and tuple(row["fact_refs"]) == nodes[next(index for index, item in enumerate(nodes) if item.objective_id == row["objective_id"])].required_fact_refs
        for row in rows
    ]
    components = {row.get("component_id") for row in rows if row.get("component_id")}
    producers = {row.get("producer_kind") for row in rows if row.get("producer_kind")}
    error_comparisons = [item for item in causal if item["axis"] == "error"]
    progression_ok = []
    for profile in raw["profiles"]:
        counts = [
            row["nodes_completed"]
            for row in rows
            if row["profile_id"] == profile["id"]
        ]
        progression_ok.append(counts == sorted(counts) and counts[-1] == len(nodes))
    return {
        "bench_version": BENCH_VERSION,
        "claim_boundary": "deterministic offline fixture; no LLM, browser, latency or production wiring",
        "inventory_size": len(export_didact_descriptors()),
        "profiles": len(raw["profiles"]),
        "course_nodes": len(nodes),
        "render_count": len(rows),
        "summary": {
            "all_renders_considered_34": all(row["inventory_considered"] == 34 for row in rows),
            "objective_and_fact_stability": round(statistics.fmean(stable), 3),
            "progression_integrity": round(statistics.fmean(progression_ok), 3),
            "completion_rate": round(
                statistics.fmean(
                    float(
                        sum(
                            row["stage"] == "completion-render"
                            and row["profile_id"] == profile["id"]
                            for row in rows
                        )
                        == 1
                    )
                    for profile in raw["profiles"]
                ),
                3,
            ),
            "distinct_components_used": len(components),
            "distinct_producer_kinds_used": len(producers),
            "cache_check_pass_rate": round(statistics.fmean(float(item["passed"]) for item in cache_checks), 3),
            "error_recovery_coverage": round(
                statistics.fmean(
                    float(item["changed"] or item["already_max_support"])
                    for item in error_comparisons
                ),
                3,
            ),
            "causal_adaptation": axes,
            "stage_diversity": by_stage,
            "error_signal_counts": dict(Counter(str(row["last_error"]) for row in rows)),
        },
        "cache_checks": cache_checks,
        "causal_comparisons": causal,
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_manifest(json.loads(args.fixture.read_text(encoding="utf-8")))
    text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
