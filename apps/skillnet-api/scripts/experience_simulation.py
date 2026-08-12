"""Compare profiles against current/future catalogues using the shadow planner.

Usage::

    uv run python scripts/experience_simulation.py tests/fixtures/animation-experience.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents.runtime.experience_simulation import simulate_experience  # noqa: E402
from src.agents.runtime.screen_eval import CriticalFact  # noqa: E402
from src.personalization.plan import (  # noqa: E402
    AccessibilityCapability,
    CognitiveMission,
    ComponentDescriptor,
    InferredPresentationBucket,
    LearningObjective,
    PersonalizationProjection,
    Presentation,
    ProducerKind,
    SourceFunction,
    SupportBand,
)


def _projection(raw: dict[str, Any]) -> PersonalizationProjection:
    return PersonalizationProjection(
        declared_presentations=tuple(Presentation(value) for value in raw["presentations"]),
        inferred_presentation_bucket=InferredPresentationBucket.UNKNOWN,
        support_band=SupportBand(raw["support_band"]),
        density=int(raw["density"]),
        accessibility_capabilities=frozenset(
            AccessibilityCapability(value) for value in raw.get("accessibility", [])
        ),
    )


def _component(raw: dict[str, Any]) -> ComponentDescriptor:
    return ComponentDescriptor(
        component_id=str(raw["id"]),
        version=int(raw.get("version", 1)),
        missions=frozenset(CognitiveMission(value) for value in raw["missions"]),
        source_functions=frozenset(SourceFunction(value) for value in raw["source_functions"]),
        presentations=frozenset(Presentation(value) for value in raw["presentations"]),
        producer_kind=ProducerKind(raw.get("producer_kind", "deterministic")),
        affordances=frozenset(map(str, raw.get("affordances", []))),
        evidence_events=frozenset(map(str, raw.get("evidence_events", []))),
        state_model_ref=raw.get("state_model_ref"),
        requirements=frozenset(map(str, raw.get("requirements", []))),
        accessibility=frozenset(
            AccessibilityCapability(value) for value in raw.get("accessibility", [])
        ),
        rank=int(raw.get("rank", 100)),
    )


def run_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    raw_objective = manifest["objective"]
    objective = LearningObjective(
        objective_id=str(raw_objective["id"]),
        objective_version=int(raw_objective.get("version", 1)),
        mission=CognitiveMission(raw_objective["mission"]),
        source_functions=frozenset(
            SourceFunction(value) for value in raw_objective["source_functions"]
        ),
        available_requirements=frozenset(map(str, raw_objective.get("requirements", []))),
        required_fact_refs=tuple(map(str, raw_objective.get("required_fact_refs", []))),
    )
    facts = tuple(
        CriticalFact(id=str(fact["id"]), any_of=tuple(map(str, fact["any_of"])))
        for fact in raw_objective.get("critical_facts", [])
    )

    results: list[dict[str, Any]] = []
    for catalogue_id, raw_catalogue in manifest["catalogues"].items():
        catalogue = tuple(_component(raw) for raw in raw_catalogue)
        for raw_profile in manifest["profiles"]:
            result = simulate_experience(
                objective=objective,
                projection=_projection(raw_profile),
                profile_id=str(raw_profile["id"]),
                catalogue_id=str(catalogue_id),
                catalogue=catalogue,
                desired_affordances=frozenset(map(str, raw_profile["desired_affordances"])),
                evidence_text=str(raw_objective["evidence_text"]),
                critical_facts=facts,
            )
            results.append(result.as_dict())

    summaries: dict[str, dict[str, Any]] = {}
    for catalogue_id in manifest["catalogues"]:
        items = [result for result in results if result["catalogue_id"] == catalogue_id]
        count = len(items)
        summaries[str(catalogue_id)] = {
            "runs": count,
            "plan_success_rate": sum(not result["declined"] for result in items) / count,
            "preference_satisfaction_rate": sum(
                result["preference_satisfied"] for result in items
            )
            / count,
            "mean_experiential_affordance_coverage": sum(
                result["experiential_affordance_coverage"] for result in items
            )
            / count,
        }
    return {"objective": objective.objective_id, "summaries": summaries, "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="Simula selección por capacidades sin LLM")
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
