"""Offline stability and sensitivity checks for the facets shortlist policy."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import statistics
import sys
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.didact_shortlist_experiment import (  # noqa: E402
    _coverage,
    _rank,
    _snapshot_documents,
    filter_catalog,
    load_fixture,
)
from src.personalization.didact_descriptors import export_didact_descriptors  # noqa: E402
from src.personalization.plan import PersonalizationProjection, Presentation  # noqa: E402


BENCH_VERSION = "didact-facets-sensitivity/1"
TIE_EPSILON = 1e-9


def _ids(shortlist: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(item["component_id"] for item in shortlist)


def _churn(left: tuple[str, ...], right: tuple[str, ...]) -> float:
    union = set(left) | set(right)
    return len(set(left) ^ set(right)) / len(union) if union else 0.0


def _dynamic_shortlist(case: Any, eligible: tuple[Any, ...], documents: Mapping[str, Any]) -> tuple[list[dict[str, Any]], str]:
    ranked = _rank("facets-top5", case, eligible, documents, 5)
    if len(ranked) <= 3:
        return ranked, "eligible<=3"
    first = ranked[:3]
    selected_actions = set().union(
        *(item.affordances for item in eligible if item.component_id in set(_ids(first)))
    )
    missing_action = not case.desired_affordances <= selected_actions
    cutoff_tied = abs(ranked[2]["scores"]["total"] - ranked[3]["scores"]["total"]) <= TIE_EPSILON
    if missing_action or cutoff_tied:
        return ranked, "missing-affordance" if missing_action else "cutoff-tie"
    return first, "confident-top3"


def _quality(cases: tuple[Any, ...], catalog: tuple[Any, ...], documents: Mapping[str, Any], policy: str) -> dict[str, Any]:
    by_id = {item.component_id: item for item in catalog}
    rows = []
    for experiment_case in cases:
        case = experiment_case.selection
        eligible, _ = filter_catalog(case, catalog)
        if policy == "k3":
            shortlist, reason = _rank("facets-top5", case, eligible, documents, 3), "fixed"
        elif policy == "k5":
            shortlist, reason = _rank("facets-top5", case, eligible, documents, 5), "fixed"
        else:
            shortlist, reason = _dynamic_shortlist(case, eligible, documents)
        selected = set(_ids(shortlist))
        actions = set().union(*(by_id[item].affordances for item in selected)) if selected else set()
        rows.append({
            "case_id": case.case_id,
            "size": len(shortlist),
            "reason": reason,
            "shortlist": list(_ids(shortlist)),
            "recall": _coverage(selected, case.relevant_components),
            "preference": _coverage(selected, experiment_case.preferred_components),
            "evidence": _coverage(selected, experiment_case.evidence_components),
            "affordance": _coverage(actions, case.desired_affordances),
        })
    return {
        "mean_size": statistics.fmean(item["size"] for item in rows),
        "mean_recall": statistics.fmean(item["recall"] for item in rows),
        "mean_preference": statistics.fmean(item["preference"] for item in rows),
        "mean_evidence": statistics.fmean(item["evidence"] for item in rows),
        "mean_affordance": statistics.fmean(item["affordance"] for item in rows),
        "expansion_count": sum(item["reason"] in {"cutoff-tie", "missing-affordance"} for item in rows),
        "rows": rows,
    }


def _wording_stability(cases: tuple[Any, ...], catalog: tuple[Any, ...], documents: Mapping[str, Any]) -> dict[str, Any]:
    churn = []
    exact = 0
    for experiment_case in cases:
        case = experiment_case.selection
        eligible, _ = filter_catalog(case, catalog)
        baseline = _ids(_rank("facets-top5", case, eligible, documents, 5))
        variants = (
            replace(case, intent_text=case.intent_text.upper() + " !"),
            replace(case, query_terms=tuple(reversed(case.query_terms))),
            replace(case, intent_text="En otras palabras: " + case.intent_text, query_terms=case.query_terms + ("learner",)),
        )
        for variant in variants:
            candidate = _ids(_rank("facets-top5", variant, eligible, documents, 5))
            value = _churn(baseline, candidate)
            churn.append(value)
            exact += value == 0
    return {
        "perturbations": len(churn),
        "exact_match_rate": exact / len(churn),
        "mean_churn": statistics.fmean(churn),
        "max_churn": max(churn),
    }


def _preference_causality(cases: tuple[Any, ...], catalog: tuple[Any, ...], documents: Mapping[str, Any]) -> dict[str, Any]:
    probes = {
        "visual-labelling": Presentation.TEXT,
        "source-evidence": Presentation.DIAGRAM,
        "symbolic-math": Presentation.DIAGRAM,
        "systems-simulation": Presentation.TEXT,
    }
    rows = []
    for experiment_case in cases:
        case = experiment_case.selection
        if case.case_id not in probes:
            continue
        target = probes[case.case_id]
        eligible, _ = filter_catalog(case, catalog)
        baseline = _ids(_rank("facets-top5", case, eligible, documents, 3))
        changed_projection = PersonalizationProjection(
            declared_presentations=(target,),
            accessibility_capabilities=case.projection.accessibility_capabilities,
        )
        changed = replace(case, projection=changed_projection)
        candidate = _ids(_rank("facets-top5", changed, eligible, documents, 3))
        supporting = {item.component_id for item in eligible if target in item.presentations}
        before = len(set(baseline) & supporting) / len(baseline) if baseline else 0.0
        after = len(set(candidate) & supporting) / len(candidate) if candidate else 0.0
        rows.append({
            "case_id": case.case_id,
            "target_presentation": target.value,
            "before_share": before,
            "after_share": after,
            "lift": after - before,
            "churn": _churn(baseline, candidate),
        })
    return {
        "probes": len(rows),
        "mean_target_share_lift": statistics.fmean(item["lift"] for item in rows),
        "mean_churn": statistics.fmean(item["churn"] for item in rows),
        "non_negative_lift_rate": sum(item["lift"] >= 0 for item in rows) / len(rows),
        "rows": rows,
    }


def _hard_gate_invariants(cases: tuple[Any, ...], catalog: tuple[Any, ...], documents: Mapping[str, Any]) -> dict[str, Any]:
    checked = 0
    violations = []
    for experiment_case in cases:
        case = experiment_case.selection
        available = case.objective.available_requirements
        if not available:
            continue
        restricted = replace(
            case,
            objective=replace(case.objective, available_requirements=frozenset()),
        )
        eligible, _ = filter_catalog(restricted, catalog)
        selected = (
            _ids(_rank("facets-top5", restricted, eligible, documents, 5))
            if eligible
            else ()
        )
        checked += 1
        for component_id in selected:
            descriptor = next(item for item in catalog if item.component_id == component_id)
            if descriptor.requirements:
                violations.append({"case_id": case.case_id, "component_id": component_id})
    return {"profiles_checked": checked, "violations": violations, "pass": not violations}


def run_sensitivity(raw: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    _, cases = load_fixture(raw)
    catalog = export_didact_descriptors()
    documents = _snapshot_documents(snapshot)
    return {
        "bench_version": BENCH_VERSION,
        "fixture_id": raw.get("fixture_id"),
        "catalog_size": len(catalog),
        "wording_stability": _wording_stability(cases, catalog, documents),
        "preference_causality": _preference_causality(cases, catalog, documents),
        "hard_gate_invariants": _hard_gate_invariants(cases, catalog, documents),
        "policies": {
            policy: _quality(cases, catalog, documents, policy)
            for policy in ("k3", "k5", "dynamic-3-to-5")
        },
        "dynamic_rule": {
            "start_k": 3,
            "expand_to": 5,
            "expand_if": ["desired affordance missing", "rank 3 and 4 have equal facet score"],
            "tie_epsilon": TIE_EPSILON,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--snapshot", type=Path, default=Path("src/personalization/didact_snapshot.json"))
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = run_sensitivity(
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
