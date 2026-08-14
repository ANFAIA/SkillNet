"""Phase 0 oracle plus real deterministic adaptive-episode planning rounds.

The trajectory specimens remain reference contracts. A separate implementation round
executes the real ``direct_episode`` adapter without an LLM, database or activity authoring.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import AsyncMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "apps" / "skillnet-api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from src.agents.runtime import nodes as runtime_nodes  # noqa: E402
from src.agents.runtime.graph import route_after_direct_episode  # noqa: E402
from src.knowledge_pack.contracts import (  # noqa: E402
    EvidenceSpec,
    MustPreserveAtom,
    MustPreserveKind,
    NodeKnowledgePack,
    PackProvenance,
    PackStatus,
    SourceRef,
)
from src.knowledge_pack.runtime_selection import select_runtime_knowledge  # noqa: E402
from src.personalization.plan import (  # noqa: E402
    CognitiveMission,
    LearningObjective,
    SourceFunction,
)


DEFAULT_FIXTURE = Path(__file__).with_name("phase0_episode_benchmark.json")


def load_fixture(path: Path = DEFAULT_FIXTURE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_fixture(fixture: dict[str, Any]) -> None:
    if fixture.get("status") != "implementation-connected-phase0":
        raise ValueError("Phase 0 must declare its limited implementation connection")
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


def _implementation_pack(case_id: str) -> NodeKnowledgePack:
    if case_id == "recognition-ready":
        mission = CognitiveMission.RECOGNIZE
        functions = frozenset({SourceFunction.LOCATE})
        kind = MustPreserveKind.FACT
        requirements = frozenset()
    elif case_id == "ticket-critical-support":
        mission = CognitiveMission.DECIDE
        functions = frozenset({SourceFunction.PROCEDURE})
        kind = MustPreserveKind.SAFETY_RULE
        requirements = frozenset()
    elif case_id == "sql-execution-support":
        mission = CognitiveMission.PRODUCE
        functions = frozenset({SourceFunction.ASSESS, SourceFunction.EXPLORE})
        kind = MustPreserveKind.CRITERION
        requirements = frozenset({"execution"})
    else:
        raise ValueError(f"unknown implementation case: {case_id}")
    node_id = f"phase0-{case_id}"
    return NodeKnowledgePack(
        status=PackStatus.READY,
        node_id=node_id,
        title=f"Phase 0 {case_id}",
        objective=LearningObjective(
            objective_id=node_id,
            objective_version=1,
            mission=mission,
            source_functions=functions,
            required_fact_refs=("fact.one",),
            available_requirements=requirements,
        ),
        source_refs=(
            SourceRef(
                ref_id="source.one",
                document_id="phase0-source-v1",
                locator="section:one",
                excerpt_hash="a" * 64,
                source_revision="rev-1",
            ),
        ),
        evidence_specs=(
            EvidenceSpec(
                evidence_id="evidence.one",
                description="Grounded observable evidence",
                atom_refs=("fact.one",),
            ),
        ),
        must_preserve=(
            MustPreserveAtom(
                atom_id="fact.one",
                kind=kind,
                text="Grounded source fact used by the real adapter.",
                sources=("source.one",),
                evidence=("evidence.one",),
                critical=kind is MustPreserveKind.SAFETY_RULE,
            ),
        ),
        provenance=PackProvenance(
            node_id=node_id,
            schema_version=1,
            source_bundle_hash="a" * 64,
            semantic_hash="b" * 64,
            generator="phase0-harness/1",
        ),
    )


def _implementation_state(pack: NodeKnowledgePack, *, criticality: str) -> dict[str, Any]:
    selection = select_runtime_knowledge(
        pack.canonical_payload(),
        profile=SimpleNamespace(
            experience_level="some",
            preset="standard",
            format_vector={},
            learning_preferences={},
            nodes_completed=1,
        ),
        node_state=SimpleNamespace(scaffold_band="neutral", last_error_kind=None),
        accessibility={},
        base_density=3,
    )
    if selection is None:
        raise RuntimeError("phase0 fixture did not produce a runtime selection")
    return {
        "request_id": f"bench-{pack.node_id}",
        "node": {
            "id": pack.node_id,
            "title": pack.title,
            "outcome": pack.title,
            "domain": pack.node_id,
            "criticality": criticality,
        },
        "profile": {
            "experience_level": "some",
            "preset": "standard",
            "format_vector": {},
            "learning_preferences": {},
            "nodes_completed": 1,
        },
        "node_state": {"mastery": 0.2, "scaffold_band": "neutral"},
        "accessibility": {},
        "effective_density": 3,
        "scaffold_band": "neutral",
        "selection_strategy": "top5/v1",
        "knowledge_pack_key": selection.cache_fragment,
        "knowledge_pack_hash": selection.pack_hash,
        "knowledge_selection_hash": selection.selection_hash,
        "knowledge_atom_ids": list(selection.atom_ids),
        "knowledge_evidence_ids": list(selection.evidence_ids),
        "knowledge_pack_payload": selection.pack_payload,
        "knowledge_source_refs": [
            item.model_dump(mode="json") for item in selection.source_refs
        ],
        "source_context": selection.source_context,
    }


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * fraction + 0.9999)))
    return ordered[index]


async def _measure_implementation_case(
    case_id: str,
    *,
    criticality: str,
    warmup_runs: int,
    measured_runs: int,
) -> tuple[dict[str, Any], list[float]]:
    pack = _implementation_pack(case_id)
    state = _implementation_state(pack, criticality=criticality)
    result: dict[str, Any] = {}
    samples: list[float] = []
    with (
        patch.object(runtime_nodes, "publish_step", AsyncMock()),
        patch.object(runtime_nodes.sse, "publish", AsyncMock()),
    ):
        for index in range(warmup_runs + measured_runs):
            started = time.perf_counter_ns()
            result = await runtime_nodes.direct_episode(state)
            elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
            if index >= warmup_runs:
                samples.append(elapsed_ms)
    return result, samples


def run_implementation_rounds(fixture: dict[str, Any]) -> dict[str, Any]:
    """Execute only deterministic planning; never generation, authoring or persistence."""

    measurement = fixture["latency_measurement"]
    definitions = (
        ("recognition-ready", "recommended", "ready", None),
        (
            "ticket-critical-support",
            "critical",
            "support_only",
            "evidence_policy:critical_oracle_unavailable",
        ),
        (
            "sql-execution-support",
            "recommended",
            "support_only",
            "evidence_policy:execution_oracle_unavailable",
        ),
    )

    async def execute() -> list[dict[str, Any]]:
        rows = []
        for case_id, criticality, expected_status, expected_reason in definitions:
            result, samples = await _measure_implementation_case(
                case_id,
                criticality=criticality,
                warmup_runs=int(measurement["warmup_runs"]),
                measured_runs=int(measurement["measured_runs"]),
            )
            status = str(result.get("episode_status"))
            reason = result.get("episode_decline_reason")
            route = route_after_direct_episode(result)
            legacy_fallback = status == "declined" and route == "declined"
            p50 = statistics.median(samples)
            p95 = _percentile(samples, 0.95)
            outcome_passed = status == expected_status and reason == expected_reason
            rows.append(
                {
                    "case_id": case_id,
                    "expected_status": expected_status,
                    "actual_status": status,
                    "expected_decline_reason": expected_reason,
                    "actual_decline_reason": reason,
                    "graph_route": route,
                    "legacy_fallback_target": (
                        "decide_formato" if legacy_fallback else None
                    ),
                    "outcome_gate_passed": outcome_passed,
                    "latency_ms": {
                        "p50": round(p50, 4),
                        "p95": round(p95, 4),
                        "samples": len(samples),
                    },
                    "latency_gate_passed": p95 <= fixture["latency_budget_ms"],
                }
            )
        return rows

    rows = asyncio.run(execute())
    return {
        "stage": "deterministic_direct_episode_planning",
        "implementation": "src.agents.runtime.nodes.direct_episode",
        "excludes": [
            "LLM generation",
            "runtime activity authoring",
            "database persistence",
            "browser rendering",
            "total learner-visible latency",
        ],
        "latency_gate_active": True,
        "latency_budget_ms": fixture["latency_budget_ms"],
        "rounds": rows,
        "passed": all(
            row["outcome_gate_passed"] and row["latency_gate_passed"]
            for row in rows
        ),
    }


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
    implementation = run_implementation_rounds(fixture)
    # A failing baseline is a benchmark finding, not a broken harness. Phase 0 is ready
    # when expected contracts and the limited real planning round both clear their gates.
    contracts_ready = all(
        domain["evaluations"]["episodic_contract"]["passed"]
        for domain in domains
    )
    return {
        "schema_version": fixture["schema_version"],
        "benchmark_id": fixture["benchmark_id"],
        "status": fixture["status"],
        "disclaimer": fixture["disclaimer"],
        "benchmark_ready": contracts_ready and implementation["passed"],
        "latency_budget_ms": fixture["latency_budget_ms"],
        "latency_measurement": fixture["latency_measurement"],
        "latency_gate_active": True,
        "latency_gate_scope": implementation["stage"],
        "implementation_round": implementation,
        "domains": domains,
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 0 - ScreenScheme versus episodic contract",
        "",
        f"- Benchmark ready: **{'PASS' if report['benchmark_ready'] else 'FAIL'}**",
        f"- Status: `{report['status']}`",
        f"- Latency gate active: `{str(report['latency_gate_active']).lower()}`",
        f"- Latency gate scope: `{report['latency_gate_scope']}`",
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
        "## Real implementation round",
        "",
        "| Case | Result | Legacy fallback | p50 ms | p95 ms |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in report["implementation_round"]["rounds"]:
        lines.append(
            f"| {row['case_id']} | {'PASS' if row['outcome_gate_passed'] else 'FAIL'} "
            f"| {row['legacy_fallback_target'] or '-'} "
            f"| {row['latency_ms']['p50']:.4f} | {row['latency_ms']['p95']:.4f} |"
        )
    lines += [
        "",
        "The active latency gate measures deterministic `direct_episode` planning only. It",
        "does not measure LLM generation, activity authoring, persistence, browser work or",
        "total learner-visible latency.",
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
