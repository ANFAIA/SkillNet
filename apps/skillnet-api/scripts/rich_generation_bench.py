#!/usr/bin/env python
"""Reproducible offline screen-strategy experiment over the pinned Didact inventory.

This is deliberately a fixture experiment, not evidence about a real LLM.  It models a
small decoder with a fixed decision budget and seeded distraction.  The useful claim is
comparative: with the same scenarios, profiles and seeds, how much does each information
boundary help or hurt?  No network, database or provider content is used.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import time
from typing import Any, Iterable


BENCH_VERSION = "rich-generation/1"
ARMS = (
    "legacy",
    "full-catalog",
    "shortlist",
    "intent-activity",
    "intent-schema-activity",
)
SNAPSHOT = Path(__file__).parents[1] / "src/personalization/didact_snapshot.json"
DEFAULT_FIXTURE = Path(__file__).parents[1] / "tests/fixtures/rich-generation-v1.json"


@dataclass(frozen=True)
class Component:
    id: str
    description: str
    purposes: frozenset[str]
    actions: frozenset[str]
    representations: frozenset[str]
    capabilities: frozenset[str]
    required_fields: tuple[str, ...] = ()

    @property
    def evidence(self) -> frozenset[str]:
        values: set[str] = set()
        for capability in self.capabilities:
            prefix = capability.split(":", 1)[0]
            if prefix in {"response", "result", "feedback", "artifact", "execution"}:
                values.add(prefix)
        return frozenset(values)


@dataclass(frozen=True)
class Observation:
    selected: tuple[str, ...]
    actions: frozenset[str]
    representations: frozenset[str]
    evidence: frozenset[str]
    depth: int
    valid: bool
    grounded: bool
    declined: bool
    prompt_tokens: int
    output_tokens: int
    latency_ms: float


def _ratio(hit: int, wanted: int) -> float:
    return hit / wanted if wanted else 1.0


def _tokens(text: str) -> set[str]:
    return {
        token.strip(".,:;()[]").lower()
        for token in text.replace("-", " ").split()
        if len(token.strip(".,:;()[]")) > 2
    }


def load_components(path: Path = SNAPSHOT) -> tuple[Component, ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    manifests = {item["id"]: item for item in raw["manifests"]}
    components = []
    for item in raw["available_types"]:
        manifest = manifests[item["manifest_id"]]
        facets = manifest.get("facets", {})
        components.append(
            Component(
                id=item["id"],
                description=str(manifest.get("description", "")),
                purposes=frozenset(facets.get("purposes", [])),
                actions=frozenset(facets.get("learnerActions", [])),
                representations=frozenset(facets.get("representations", [])),
                capabilities=frozenset(manifest.get("capabilities", [])),
                required_fields=tuple(
                    str(field["key"])
                    for field in manifest.get("authoring", {}).get("fields", [])
                    if field.get("required") and field.get("key")
                ),
            )
        )
    return tuple(components)


def _score(component: Component, scenario: dict[str, Any], profile: dict[str, Any]) -> float:
    actions = set(scenario["actions"])
    reps = set(scenario["representations"])
    purposes = set(scenario["purposes"])
    preferred = set(profile["preferred_representations"])
    evidence = set(scenario["evidence"])
    return (
        0.32 * _ratio(len(actions & component.actions), len(actions))
        + 0.18 * _ratio(len(reps & component.representations), len(reps))
        + 0.15 * _ratio(len(purposes & component.purposes), len(purposes))
        + 0.20 * _ratio(len(evidence & component.evidence), len(evidence))
        + 0.15 * _ratio(len(preferred & component.representations), len(preferred))
    )


def _rank(
    components: Iterable[Component], scenario: dict[str, Any], profile: dict[str, Any]
) -> list[tuple[float, Component]]:
    return sorted(
        ((_score(component, scenario, profile), component) for component in components),
        key=lambda item: (-item[0], item[1].id),
    )


def _rng(seed: int, *parts: str) -> random.Random:
    key = ":".join((str(seed), *parts)).encode()
    return random.Random(int(hashlib.sha256(key).hexdigest()[:16], 16))


def _legacy_component(scenario: dict[str, Any]) -> Component:
    reps = set(scenario["representations"])
    actions = set(scenario["actions"])
    if "numeric" in reps:
        component_id, representation, affordance = "Table", "table", "inspect"
    elif "order" in actions:
        component_id, representation, affordance = "StepSequence", "text", "inspect"
    else:
        component_id, representation, affordance = "QuizItem", "text", "select"
    return Component(
        id=component_id,
        description="legacy fixture",
        purposes=frozenset({"present", "assess"}),
        actions=frozenset({affordance, "respond"} if component_id == "QuizItem" else {affordance}),
        representations=frozenset({representation}),
        capabilities=frozenset(
            {"response:choice", "result:scored", "feedback:immediate"}
            if component_id == "QuizItem"
            else {"response:none", "result:none"}
        ),
    )


def _choose(
    arm: str,
    components: tuple[Component, ...],
    scenario: dict[str, Any],
    profile: dict[str, Any],
    seed: int,
) -> tuple[Component, ...]:
    if arm == "legacy":
        return (_legacy_component(scenario),)
    ranked = _rank(components, scenario, profile)
    rng = _rng(seed, arm, scenario["id"], profile["id"])
    if arm == "full-catalog":
        # A small decoder looking at every contract is more distractible: noise is
        # intentionally seeded and can move a plausible-but-weaker component upward.
        noisy = sorted(
            ((score + rng.uniform(-0.24, 0.24), component) for score, component in ranked),
            key=lambda item: (-item[0], item[1].id),
        )
        return (noisy[0][1],)
    shortlist = ranked[:5]
    if arm == "shortlist":
        bounded = sorted(
            ((score + rng.uniform(-0.05, 0.05), component) for score, component in shortlist),
            key=lambda item: (-item[0], item[1].id),
        )
        return (bounded[0][1],)
    if arm not in {"intent-activity", "intent-schema-activity"}:
        raise ValueError(f"unknown arm {arm}")
    if arm == "intent-activity" and scenario.get("regression_component"):
        forced = next(
            item for item in components if item.id == scenario["regression_component"]
        )
        return (forced,)
    primary = shortlist[0][1]
    # Composition is allowed only when the second activity contributes a missing action,
    # representation or evidence channel. This is richness with a job, not decoration.
    covered = primary.actions | primary.representations | primary.evidence
    desired = (
        set(scenario["actions"])
        | set(scenario["representations"])
        | set(scenario["evidence"])
    )
    second = next(
        (
            component
            for _score_value, component in shortlist[1:]
            if (component.actions | component.representations | component.evidence)
            & (desired - covered)
        ),
        None,
    )
    if second is None:
        return (primary,)
    # Novices receive guided complement; experienced learners receive a second activity
    # only at depth 4, preventing complexity from becoming the metric itself.
    if profile["support"] == "guided" or int(scenario["target_depth"]) >= 4:
        return (primary, second)
    return (primary,)


def _guided_definition(component: Component, scenario: dict[str, Any]) -> dict[str, Any]:
    """Minimal schema-shaped fixture, sourced only from declared pack facts."""
    facts = list(scenario["source_facts"])
    definition: dict[str, Any] = {
        "title": scenario["title"],
        "source_refs": facts,
    }
    list_fields = {
        "series", "nodes", "relations", "targets", "items", "tools", "segments",
        "categories", "claims", "files",
    }
    text_fields = {"prompt", "instructions", "initialExpression", "unit", "unitPolicy", "kind"}
    for field in component.required_fields:
        if field in list_fields:
            definition[field] = [
                {"id": f"{field}-1", "label": facts[0], "value": 1},
                {"id": f"{field}-2", "label": facts[1], "value": 2},
            ]
        elif field in text_fields:
            values = {
                "unit": "unidad",
                "unitPolicy": "required",
                "kind": "linear",
                "initialExpression": facts[0],
            }
            definition[field] = values.get(field, f"{scenario['title']}: {facts[0]}")
        else:
            definition[field] = {"value": facts[0], "source_ref": facts[0]}
    return definition


def _definition(arm: str, component: Component, scenario: dict[str, Any]) -> dict[str, Any]:
    if arm == "intent-activity" and scenario.get("regression_definition"):
        return dict(scenario["regression_definition"])
    if arm == "intent-schema-activity":
        return _guided_definition(component, scenario)
    return {
        "title": scenario["title"],
        "description": f"Actividad sobre {scenario['source_facts'][0]}",
        "steps": list(scenario["source_facts"][:3]),
        "source_refs": list(scenario["source_facts"]),
    }


def _definition_valid(component: Component, definition: dict[str, Any]) -> bool:
    for field in component.required_fields:
        if definition.get(field) in (None, "", [], {}):
            return False
    # Explicit semantic guard for the blank-render regression reported in the real UI.
    if component.id == "didact.data-explorer" and not definition.get("series"):
        return False
    return True


def _observe(
    arm: str,
    selected: tuple[Component, ...],
    scenario: dict[str, Any],
    profile: dict[str, Any],
    elapsed_ms: float,
    inventory: tuple[Component, ...],
) -> Observation:
    actions = frozenset().union(*(item.actions for item in selected))
    reps = frozenset().union(*(item.representations for item in selected))
    evidence = frozenset().union(*(item.evidence for item in selected))
    facts = tuple(scenario["source_facts"])
    candidates = [item.id for item in selected]
    prompt = json.dumps(
        {
            "title": scenario["title"],
            "intent": {
                "actions": scenario["actions"],
                "evidence": scenario["evidence"],
                "representations": scenario["representations"],
                "depth": scenario["target_depth"],
            }
            if arm.startswith("intent-")
            else None,
            "profile": profile,
            "candidate_component_ids": (
                candidates if arm != "full-catalog" else [item.id for item in inventory]
            ),
            "allowed_source_refs": facts,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    # Fixture output mirrors the server-owned activity boundary: component ids must have
    # been offered and every source reference must come from the pack.
    definitions = [_definition(arm, item, scenario) for item in selected]
    output = {
        "activities": [
            {
                "component_id": item.id,
                "definition": definition,
                "source_refs": list(definition.get("source_refs", [])),
            }
            for item, definition in zip(selected, definitions, strict=True)
        ]
    }
    valid = bool(selected) and all(
        activity["component_id"] in candidates
        and _definition_valid(item, activity["definition"])
        and set(activity["source_refs"]) <= set(facts)
        for item, activity in zip(selected, output["activities"], strict=True)
    )
    serialized = json.dumps(output, ensure_ascii=False).lower()
    unsupported = {
        term.lower()
        for term in scenario.get("unsupported_terms", [])
        if term.lower() in serialized
    }
    grounded = bool(facts) and not unsupported and all(
        set(activity["source_refs"]) == set(facts) for activity in output["activities"]
    )
    raw_depth = 1
    if actions & {"manipulate", "construct", "calculate", "decide", "execute", "experiment"}:
        raw_depth = 3
    if actions & {"create", "explain"} or len(selected) > 1:
        raw_depth = 4
    return Observation(
        selected=tuple(item.id for item in selected),
        actions=actions,
        representations=reps,
        evidence=evidence,
        depth=raw_depth,
        valid=valid,
        grounded=grounded,
        declined=not selected,
        prompt_tokens=math.ceil(len(prompt) / 4),
        output_tokens=math.ceil(len(json.dumps(output, ensure_ascii=False)) / 4),
        latency_ms=elapsed_ms,
    )


def _row_metrics(observation: Observation, scenario: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    wanted_actions = set(scenario["actions"])
    wanted_reps = set(scenario["representations"])
    wanted_evidence = set(scenario["evidence"])
    preferred = set(profile["preferred_representations"])
    target_depth = int(scenario["target_depth"])
    dimensions = {
        "affordance_coverage": _ratio(len(wanted_actions & observation.actions), len(wanted_actions)),
        "evidence_coverage": _ratio(len(wanted_evidence & observation.evidence), len(wanted_evidence)),
        "theme_fit": _ratio(len(wanted_reps & observation.representations), len(wanted_reps)),
        "preference_fit": _ratio(len(preferred & observation.representations), len(preferred)),
        "depth_fit": max(0.0, 1.0 - abs(target_depth - observation.depth) / 4),
    }
    score = 100 * (
        0.28 * dimensions["affordance_coverage"]
        + 0.24 * dimensions["evidence_coverage"]
        + 0.20 * dimensions["theme_fit"]
        + 0.12 * dimensions["preference_fit"]
        + 0.16 * dimensions["depth_fit"]
    )
    gate = observation.valid and observation.grounded and not observation.declined
    return {
        **dimensions,
        "candidate_quality": round(score, 2),
        "quality": round(score, 2) if gate else None,
        "gate_passed": gate,
    }


def _entropy(signatures: Iterable[tuple[str, ...]]) -> float:
    counts = Counter(signatures)
    total = sum(counts.values())
    return -sum((count / total) * math.log2(count / total) for count in counts.values()) if total else 0.0


def run_manifest(raw: dict[str, Any], components: tuple[Component, ...] | None = None) -> dict[str, Any]:
    if raw.get("version") != BENCH_VERSION:
        raise ValueError(f"fixture version must be {BENCH_VERSION}")
    inventory = components or load_components()
    rows: list[dict[str, Any]] = []
    for scenario in raw["scenarios"]:
        for profile in raw["profiles"]:
            for seed in raw["seeds"]:
                for arm in ARMS:
                    started = time.perf_counter_ns()
                    selected = _choose(arm, inventory, scenario, profile, int(seed))
                    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
                    observation = _observe(
                        arm, selected, scenario, profile, elapsed_ms, inventory
                    )
                    rows.append(
                        {
                            "scenario": scenario["id"],
                            "profile": profile["id"],
                            "seed": seed,
                            "arm": arm,
                            "selected": list(observation.selected),
                            "semantic_signature": [
                                *sorted(observation.actions),
                                "|",
                                *sorted(observation.evidence),
                                "|",
                                *sorted(observation.representations),
                                f"depth:{observation.depth}",
                            ],
                            "metrics": _row_metrics(observation, scenario, profile),
                            "valid": observation.valid,
                            "grounded": observation.grounded,
                            "declined": observation.declined,
                            "prompt_tokens": observation.prompt_tokens,
                            "output_tokens": observation.output_tokens,
                            "latency_ms": observation.latency_ms,
                            "cost_usd": 0.0,
                        }
                    )

    summaries: dict[str, Any] = {}
    for arm in ARMS:
        arm_rows = [row for row in rows if row["arm"] == arm]
        quality = [row["metrics"]["quality"] for row in arm_rows if row["metrics"]["quality"] is not None]
        candidate_quality = [row["metrics"]["candidate_quality"] for row in arm_rows]
        signatures = [tuple(row["semantic_signature"]) for row in arm_rows]
        selected_types = {item for row in arm_rows for item in row["selected"]}
        profile_changes = 0
        profile_pairs = 0
        grouped: dict[tuple[str, int], dict[str, tuple[str, ...]]] = defaultdict(dict)
        for row in arm_rows:
            grouped[(row["scenario"], int(row["seed"]))][row["profile"]] = tuple(row["semantic_signature"])
        for values in grouped.values():
            if len(values) == 2:
                profile_pairs += 1
                profile_changes += int(len(set(values.values())) > 1)
        summaries[arm] = {
            "runs": len(arm_rows),
            "gate_pass_rate": statistics.fmean(float(row["metrics"]["gate_passed"]) for row in arm_rows),
            "mean_quality": statistics.fmean(quality) if quality else None,
            "mean_candidate_quality": statistics.fmean(candidate_quality),
            "mean_affordance_coverage": statistics.fmean(row["metrics"]["affordance_coverage"] for row in arm_rows),
            "mean_evidence_coverage": statistics.fmean(row["metrics"]["evidence_coverage"] for row in arm_rows),
            "mean_theme_fit": statistics.fmean(row["metrics"]["theme_fit"] for row in arm_rows),
            "mean_preference_fit": statistics.fmean(row["metrics"]["preference_fit"] for row in arm_rows),
            "mean_depth_fit": statistics.fmean(row["metrics"]["depth_fit"] for row in arm_rows),
            "distinct_component_types": len(selected_types),
            "semantic_signature_entropy_bits": _entropy(signatures),
            "profile_causal_change_rate": _ratio(profile_changes, profile_pairs),
            "mean_prompt_tokens": statistics.fmean(row["prompt_tokens"] for row in arm_rows),
            "mean_output_tokens": statistics.fmean(row["output_tokens"] for row in arm_rows),
            "mean_latency_ms": statistics.fmean(row["latency_ms"] for row in arm_rows),
            "declines": sum(row["declined"] for row in arm_rows),
            "invalid": sum(not row["valid"] for row in arm_rows),
            "ungrounded": sum(not row["grounded"] for row in arm_rows),
            "cost_usd": 0.0,
        }
    return {
        "bench_version": BENCH_VERSION,
        "fixture_model": raw.get("fixture_model"),
        "claim_boundary": "deterministic constrained-decoder proxy; not a real LLM quality result",
        "inventory_size": len(inventory),
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
