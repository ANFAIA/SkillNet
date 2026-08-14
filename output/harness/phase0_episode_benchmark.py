"""Phase 0 oracle for ScreenScheme versus a future episodic trajectory contract.

This is deliberately not an EpisodeDirector implementation. It evaluates immutable
specimens against the same domain contracts so future production outputs can replace
the specimens without changing the oracle.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any, Callable


DEFAULT_FIXTURE = Path(__file__).with_name("phase0_episode_benchmark.json")


def load_fixture(path: Path = DEFAULT_FIXTURE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_fixture(fixture: dict[str, Any]) -> None:
    if fixture.get("status") != "contract-only":
        raise ValueError("Phase 0 must remain explicitly contract-only")
    domain_ids: set[str] = set()
    for domain in fixture["domains"]:
        domain_id = domain["domain_id"]
        if domain_id in domain_ids:
            raise ValueError(f"duplicate domain_id: {domain_id}")
        domain_ids.add(domain_id)
        facts = set(domain["source_affordance_map"]["facts"])
        required_facts = set(domain["competency_contract"]["required_facts"])
        if not required_facts <= facts:
            raise ValueError(
                f"{domain_id} has required facts absent from SourceAffordanceMap"
            )
        if domain["transfer_task"]["task_ref"] != domain["competency_contract"][
            "transfer_task_ref"
        ]:
            raise ValueError(f"{domain_id} transfer task does not match its contract")
        paths = [specimen["path"] for specimen in domain["specimens"]]
        if sorted(paths) != ["episodic_contract", "screen_scheme"]:
            raise ValueError(f"{domain_id} must define exactly the two benchmark paths")


def _ratio(found: set[str], required: set[str]) -> float:
    return round(len(found & required) / len(required), 4) if required else 1.0


def evaluate_specimen(
    domain: dict[str, Any], specimen: dict[str, Any], *, viewport_budget_px: int
) -> dict[str, Any]:
    contract = domain["competency_contract"]
    supported_facts = set(domain["source_affordance_map"]["facts"])
    cited_facts = {
        fact_ref
        for claim in specimen["claims"]
        for fact_ref in claim.get("fact_refs", [])
        if fact_ref in supported_facts
    }
    unsupported_claims = sum(
        not claim.get("fact_refs")
        or any(ref not in supported_facts for ref in claim.get("fact_refs", []))
        for claim in specimen["claims"]
    )
    dominant_units = sum(
        len(set(unit["learner_actions"])) == 1
        and unit["dominant_action"] == unit["learner_actions"][0]
        for unit in specimen["units"]
    )
    evidence = {
        item["type"]
        for item in specimen["evidence_outputs"]
        if item.get("producible") is True
    }
    viewport_units = sum(
        unit["estimated_height_px"] <= viewport_budget_px
        for unit in specimen["units"]
    )
    latency_ms = specimen.get("latency_ms")
    metrics = {
        "required_fact_coverage": _ratio(
            cited_facts, set(contract["required_facts"])
        ),
        "unsupported_claims": float(unsupported_claims),
        "dominant_action_rate": round(dominant_units / len(specimen["units"]), 4),
        "evidence_producible": _ratio(
            evidence, set(contract["required_evidence"])
        ),
        "critical_error_coverage": _ratio(
            set(specimen["critical_errors_covered"]),
            set(contract["critical_errors"]),
        ),
        "transfer_task_covered": float(
            specimen.get("transfer_task_ref") == contract["transfer_task_ref"]
            and specimen.get("transfer_result") == domain["transfer_task"]["oracle"]
        ),
        "viewport_budget_rate": round(viewport_units / len(specimen["units"]), 4),
    }
    return {
        "path": specimen["path"],
        "specimen_kind": specimen["specimen_kind"],
        "metrics": metrics,
        "latency": {
            "status": "placeholder" if latency_ms is None else "measured",
            "value_ms": latency_ms,
        },
    }


def _gate_passes(actual: float, operator: str, threshold: float) -> bool:
    operations: dict[str, Callable[[float, float], bool]] = {
        "eq": lambda left, right: left == right,
        "gte": lambda left, right: left >= right,
        "lte": lambda left, right: left <= right,
    }
    return operations[operator](actual, threshold)


def attach_gates(
    evaluation: dict[str, Any], gates: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    result = copy.deepcopy(evaluation)
    result["gates"] = {
        metric: {
            **gate,
            "actual": result["metrics"][metric],
            "passed": _gate_passes(
                result["metrics"][metric], gate["operator"], gate["threshold"]
            ),
        }
        for metric, gate in gates.items()
    }
    result["passed"] = all(gate["passed"] for gate in result["gates"].values())
    return result


def run(fixture: dict[str, Any]) -> dict[str, Any]:
    validate_fixture(fixture)
    domains = []
    for domain in fixture["domains"]:
        evaluations = {
            specimen["path"]: attach_gates(
                evaluate_specimen(
                    domain,
                    specimen,
                    viewport_budget_px=fixture["viewport_budget_px"],
                ),
                fixture["gates"],
            )
            for specimen in domain["specimens"]
        }
        baseline = evaluations["screen_scheme"]["metrics"]
        expected = evaluations["episodic_contract"]["metrics"]
        domains.append(
            {
                "domain_id": domain["domain_id"],
                "title": domain["title"],
                "evaluations": evaluations,
                "contrast": {
                    "required_fact_coverage_delta": round(
                        expected["required_fact_coverage"]
                        - baseline["required_fact_coverage"],
                        4,
                    ),
                    "unsupported_claim_reduction": round(
                        baseline["unsupported_claims"]
                        - expected["unsupported_claims"],
                        4,
                    ),
                    "evidence_producible_delta": round(
                        expected["evidence_producible"]
                        - baseline["evidence_producible"],
                        4,
                    ),
                    "critical_error_coverage_delta": round(
                        expected["critical_error_coverage"]
                        - baseline["critical_error_coverage"],
                        4,
                    ),
                    "transfer_task_covered_delta": round(
                        expected["transfer_task_covered"]
                        - baseline["transfer_task_covered"],
                        4,
                    ),
                },
            }
        )
    # A failing baseline is a benchmark finding, not a broken harness. Phase 0 is ready
    # when its oracle is valid and each expected-output contract clears the gates.
    ready = all(
        domain["evaluations"]["episodic_contract"]["passed"]
        for domain in domains
    )
    return {
        "schema_version": fixture["schema_version"],
        "benchmark_id": fixture["benchmark_id"],
        "status": fixture["status"],
        "disclaimer": fixture["disclaimer"],
        "benchmark_ready": ready,
        "latency_budget_ms": fixture["latency_budget_ms"],
        "latency_measurement": fixture["latency_placeholder"],
        "latency_gate_active": False,
        "domains": domains,
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 0 - ScreenScheme versus episodic contract",
        "",
        f"- Benchmark ready: **{'PASS' if report['benchmark_ready'] else 'FAIL'}**",
        f"- Status: `{report['status']}`",
        f"- Latency gate active: `{str(report['latency_gate_active']).lower()}`",
        f"- Disclaimer: {report['disclaimer']}",
        "",
        "| Domain | ScreenScheme | Episodic expected contract |",
        "|---|---:|---:|",
    ]
    for domain in report["domains"]:
        baseline = domain["evaluations"]["screen_scheme"]
        expected = domain["evaluations"]["episodic_contract"]
        lines.append(
            f"| {domain['title']} | {'PASS' if baseline['passed'] else 'FAIL'} "
            f"| {'PASS' if expected['passed'] else 'FAIL'} |"
        )
    lines += [
        "",
        "Latency remains a placeholder and is intentionally excluded from gates until a real",
        "ScreenScheme render and a real episodic implementation are timed under the same runner.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = run(load_fixture(args.fixture))
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "summary.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (args.out / "report.md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["benchmark_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
