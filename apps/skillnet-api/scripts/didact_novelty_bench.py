#!/usr/bin/env python
"""Offline comparison of current top-5 ranking vs bounded semantic novelty over 34."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.personalization.didact_descriptors import export_didact_descriptors  # noqa: E402
from src.personalization.novelty import ranking_collapse, useful_novelty_tiebreak  # noqa: E402
from src.personalization.plan import (  # noqa: E402
    CognitiveMission,
    Declined,
    LearningObjective,
    PersonalizationProjection,
    Presentation,
    SourceFunction,
    plan_experience,
)

BENCH_VERSION = "didact-novelty/1"


def run(*, scenarios: int = 24) -> dict:
    catalog = export_didact_descriptors()
    missions = tuple(CognitiveMission)
    functions = tuple(SourceFunction)
    current_rankings = []
    novelty_rankings = []
    exposure: dict[str, int] = {}
    rows = []
    for index in range(scenarios):
        objective = LearningObjective(
            objective_id=f"case-{index}",
            objective_version=1,
            mission=missions[index % len(missions)],
            source_functions=frozenset({SourceFunction.EXPLORE, functions[index % len(functions)]}),
            # The comparison is about eligible ranking, not host readiness.
            available_requirements=frozenset(
                requirement for item in catalog for requirement in item.requirements
            ),
        )
        presentation = tuple(Presentation)[index % len(Presentation)]
        projection = PersonalizationProjection(declared_presentations=(presentation,))
        planned = plan_experience(objective, projection, catalog)
        if isinstance(planned, Declined):
            continue
        current = planned.component_candidates
        novelty = useful_novelty_tiebreak(current, prior_exposure=exposure)
        current_rankings.append(current[:5])
        novelty_rankings.append(novelty[:5])
        if novelty:
            exposure[novelty[0].component_id] = exposure.get(novelty[0].component_id, 0) + 1
        rows.append(
            {
                "scenario": objective.objective_id,
                "mission": objective.mission.value,
                "presentation": presentation.value,
                "current_top5": [item.component_id for item in current[:5]],
                "novelty_top5": [item.component_id for item in novelty[:5]],
                "eligibility_preserved": {item.component_id for item in current}
                == {item.component_id for item in novelty},
            }
        )
    return {
        "bench_version": BENCH_VERSION,
        "catalog_count": len(catalog),
        "runtime_connected": False,
        "policy": "novelty only within exact rank/presentation/producer/affordance/evidence ties",
        "current": asdict(ranking_collapse(current_rankings)),
        "bounded_novelty": asdict(ranking_collapse(novelty_rankings)),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=int, default=24)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = run(scenarios=args.scenarios)
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
