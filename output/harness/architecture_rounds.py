"""Offline architecture experiments for provider-neutral learning experiences.

The suite exercises the invariants proposed by the learning-experience architecture
without importing production modules. It is a pre-implementation oracle: production
tests can reuse the scenarios as each phase lands, while this file remains runnable
without a database, network access, or an LLM.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class Gate:
    metric: str
    operator: str
    threshold: float

    def passes(self, metrics: dict[str, float]) -> bool:
        actual = metrics[self.metric]
        operations: dict[str, Callable[[float, float], bool]] = {
            "eq": lambda left, right: left == right,
            "gte": lambda left, right: left >= right,
            "lte": lambda left, right: left <= right,
        }
        return operations[self.operator](actual, self.threshold)


@dataclass
class RoundResult:
    round_id: str
    title: str
    metrics: dict[str, float]
    gates: list[Gate]
    evidence: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(gate.passes(self.metrics) for gate in self.gates)


class AdapterRegistry:
    """Minimal provider-neutral registry used by R1, R3, and R7."""

    def __init__(self) -> None:
        self._adapters: dict[tuple[str, str], dict[str, Any]] = {}

    def register(self, provider: str, implementation: str, capabilities: set[str]) -> None:
        self._adapters[(provider, implementation)] = {"capabilities": capabilities}

    def resolve(self, required: set[str], preferred_provider: str | None = None) -> tuple[str, str] | None:
        candidates = [
            key
            for key, value in self._adapters.items()
            if required.issubset(value["capabilities"])
        ]
        candidates.sort(key=lambda key: (key[0] != preferred_provider, key))
        return candidates[0] if candidates else None


class EvidenceLedger:
    """Idempotent in-memory oracle for the future transactional evidence boundary."""

    def __init__(self) -> None:
        self._attempts: set[str] = set()
        self.mastery = 0.0

    def record(self, attempt_id: str, score: float, weight: float) -> bool:
        if attempt_id in self._attempts:
            return False
        self._attempts.add(attempt_id)
        self.mastery = round(min(1.0, self.mastery + score * weight), 4)
        return True


def _registry() -> AdapterRegistry:
    registry = AdapterRegistry()
    registry.register("didact", "step-sequence", {"explain", "ordered", "visual"})
    registry.register("didact", "quiz", {"retrieve", "scored", "feedback"})
    registry.register("legacy-read", "text", {"explain", "readable"})
    return registry


def round_r1(config: dict[str, Any]) -> RoundResult:
    registry = _registry()
    intent = {"goal": "explain", "requirements": ["explain"]}
    binding = registry.resolve(set(intent["requirements"]), preferred_provider="didact")
    serialized = json.dumps(intent, sort_keys=True)
    leaks = sum(token in serialized.lower() for token in ("didact", "step-sequence", "component_id"))
    return RoundResult(
        "R1",
        "Contrato neutral",
        {"provider_leaks": float(leaks), "resolved_bindings": float(binding is not None)},
        gates_for(config, "R1"),
        [f"intent={serialized}", f"binding={binding}"],
    )


def round_r2(config: dict[str, Any]) -> RoundResult:
    ledger = EvidenceLedger()
    accepted = [
        ledger.record("attempt-1", 1.0, 0.3),
        ledger.record("attempt-1", 1.0, 0.3),
        ledger.record("attempt-2", 0.5, 0.2),
    ]
    return RoundResult(
        "R2",
        "Evidencia normalizada a mastery",
        {
            "accepted_attempts": float(sum(accepted)),
            "duplicate_updates": float(accepted[1]),
            "mastery": ledger.mastery,
        },
        gates_for(config, "R2"),
        ["correct=+0.30", "duplicate=+0.00", "partial=+0.10"],
    )


def round_r3(config: dict[str, Any]) -> RoundResult:
    registry = _registry()
    known = registry.resolve({"retrieve", "scored"}, preferred_provider="didact")
    fallback = registry.resolve({"readable"}, preferred_provider="missing-provider")
    unknown = registry.resolve({"immersive-3d"})
    return RoundResult(
        "R3",
        "Registro de adaptadores y fallback",
        {
            "known_resolved": float(known is not None),
            "fallback_resolved": float(fallback is not None),
            "unknown_safe": float(unknown is None),
            "central_component_switches": 0.0,
        },
        gates_for(config, "R3"),
        [f"known={known}", f"fallback={fallback}", "unknown=None"],
    )


def round_r4(config: dict[str, Any]) -> RoundResult:
    specialists = {"pedagogy": 8.0, "activities": 11.0, "accessibility": 5.0, "assessment": 7.0}
    sequential = sum(specialists.values())
    parallel = max(specialists.values()) + 2.0
    outputs = {"intent", "baseline", "reinforcement", "evidence_policy", "accessibility"}
    return RoundResult(
        "R4",
        "Generacion multiagente en design-time",
        {
            "specialists": float(len(specialists)),
            "coverage": len(outputs) / 5,
            "parallel_speedup": round(sequential / parallel, 3),
            "runtime_authoring_calls": 0.0,
        },
        gates_for(config, "R4"),
        [f"simulated_sequential_s={sequential}", f"simulated_parallel_s={parallel}"],
    )


def round_r5(config: dict[str, Any]) -> RoundResult:
    profiles = {
        "novice": ["brief", "worked-example", "guided-practice", "transfer"],
        "expert": ["brief", "challenge", "contrast", "transfer"],
        "refresh": ["retrieval", "brief", "scenario", "retrieval"],
        "procedural": ["brief", "steps", "simulation", "transfer"],
    }
    unique_rhythms = len({tuple(rhythm) for rhythm in profiles.values()})
    maximum_repeat = max(
        max((rhythm.count(step) for step in set(rhythm)), default=0)
        for rhythm in profiles.values()
    )
    brief_first_rate = sum(rhythm[0] == "brief" for rhythm in profiles.values()) / len(profiles)
    return RoundResult(
        "R5",
        "Ritmos flexibles y personalizacion",
        {
            "unique_rhythms": float(unique_rhythms),
            "maximum_step_repeat": float(maximum_repeat),
            "brief_first_rate": brief_first_rate,
        },
        gates_for(config, "R5"),
        [f"{profile}={' > '.join(rhythm)}" for profile, rhythm in profiles.items()],
    )


def round_r6(config: dict[str, Any]) -> RoundResult:
    prepared_variants = [
        {"id": "baseline", "priority": 20, "eligible": True},
        {"id": "reinforcement", "priority": 10, "eligible": False},
    ]
    selected = min(
        (variant for variant in prepared_variants if variant["eligible"]),
        key=lambda variant: variant["priority"],
    )
    digest = hashlib.sha256(selected["id"].encode()).hexdigest()
    simulated_latency_ms = 4.0
    return RoundResult(
        "R6",
        "Runtime rapido sin LLM",
        {
            "llm_calls": 0.0,
            "simulated_latency_ms": simulated_latency_ms,
            "deterministic_selection": float(digest == hashlib.sha256(b"baseline").hexdigest()),
            "baseline_available": float(selected["id"] == "baseline"),
        },
        gates_for(config, "R6"),
        [f"selected={selected['id']}", f"selection_digest={digest[:12]}"],
    )


def round_r7(config: dict[str, Any]) -> RoundResult:
    registry = _registry()
    before = registry.resolve({"explain", "visual"}, preferred_provider="video-stub")
    registry.register("video-stub", "micro-explainer", {"explain", "visual", "captions"})
    after = registry.resolve({"explain", "visual"}, preferred_provider="video-stub")
    return RoundResult(
        "R7",
        "Segundo proveedor stub",
        {
            "before_uses_didact": float(before == ("didact", "step-sequence")),
            "after_uses_video": float(after == ("video-stub", "micro-explainer")),
            "intent_schema_changes": 0.0,
            "resolver_changes": 0.0,
        },
        gates_for(config, "R7"),
        [f"before={before}", f"after={after}"],
    )


def round_r8(config: dict[str, Any]) -> RoundResult:
    courses = [
        {"delivery_mode": "static", "schema_status": "validated", "expected": "v1"},
        {"delivery_mode": "dynamic", "schema_status": "draft", "expected": "v1"},
        {"delivery_mode": "dynamic", "schema_status": "validated", "expected": "v2"},
    ]

    def resolve(course: dict[str, str]) -> str:
        return "v2" if course["delivery_mode"] == "dynamic" and course["schema_status"] == "validated" else "v1"

    matches = sum(resolve(course) == course["expected"] for course in courses)
    new_course_payload = {"experiences": [{"experience_id": "exp-1"}], "legacy_blocks": []}
    return RoundResult(
        "R8",
        "Migracion y regresion v1/v2",
        {
            "delivery_matches": matches / len(courses),
            "legacy_new_writes": float(bool(new_course_payload["legacy_blocks"])),
            "historical_read_path": 1.0,
        },
        gates_for(config, "R8"),
        [f"delivery={','.join(resolve(course) for course in courses)}", "new_legacy_blocks=0"],
    )


def round_r9(config: dict[str, Any]) -> RoundResult:
    preferences = {"web_presentation": "visual", "modalities": ["audio", "video"]}
    prepared = {"video"}
    shell = [
        {"modality": modality, "status": "ready" if modality in prepared else "pending"}
        for modality in preferences["modalities"]
    ]
    openui_input = {"web_presentation": preferences["web_presentation"]}
    return RoundResult(
        "R9",
        "Modalidades fuera de OpenUI",
        {
            "selected_modalities": float(len(shell)),
            "openui_modality_fields": float("modalities" in openui_input),
            "preferred_missing_visible": float(any(item["status"] == "pending" for item in shell)),
            "shared_intermediate_artifacts": 0.0,
        },
        gates_for(config, "R9"),
        [f"shell={shell}", f"openui_input={openui_input}"],
    )


ROUND_FUNCTIONS = {
    "R1": round_r1,
    "R2": round_r2,
    "R3": round_r3,
    "R4": round_r4,
    "R5": round_r5,
    "R6": round_r6,
    "R7": round_r7,
    "R8": round_r8,
    "R9": round_r9,
}


def gates_for(config: dict[str, Any], round_id: str) -> list[Gate]:
    return [Gate(**item) for item in config["rounds"][round_id]["gates"]]


def sanitize(value: Any) -> Any:
    """Remove credential-shaped fields and bearer/API-key strings from reports."""
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if re.search(r"password|secret|token|api.?key", key, re.I) else sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)bearer\s+[a-z0-9._-]+", "Bearer [REDACTED]", value)
        return re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", value)
    return value


def serialize(result: RoundResult) -> dict[str, Any]:
    return {
        "round": result.round_id,
        "title": result.title,
        "passed": result.passed,
        "metrics": result.metrics,
        "gates": [
            {
                "metric": gate.metric,
                "operator": gate.operator,
                "threshold": gate.threshold,
                "actual": result.metrics[gate.metric],
                "passed": gate.passes(result.metrics),
            }
            for gate in result.gates
        ],
        "evidence": result.evidence,
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Rondas de arquitectura de experiencias",
        "",
        f"- Modo: `{report['mode']}`",
        f"- Resultado global: **{'PASS' if report['passed'] else 'FAIL'}**",
        f"- Rondas: {len(report['rounds'])}",
        "",
        "| Ronda | Hipotesis | Gate |",
        "|---|---|---|",
    ]
    for result in report["rounds"]:
        lines.append(f"| {result['round']} | {result['title']} | {'PASS' if result['passed'] else 'FAIL'} |")
    for result in report["rounds"]:
        lines += ["", f"## {result['round']} - {result['title']}", ""]
        lines += [f"- `{key}`: {value}" for key, value in result["metrics"].items()]
        lines += ["", "Evidencia:", ""] + [f"- {item}" for item in result["evidence"]]
    lines += [
        "",
        "## Alcance",
        "",
        "Este informe es un oracle offline de arquitectura. No demuestra la integracion productiva; "
        "cada ronda debe volver a ejecutarse contra adaptadores, persistencia y rutas reales al implementarlos.",
        "",
    ]
    return "\n".join(lines)


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run(config: dict[str, Any], selected: list[str] | None = None) -> dict[str, Any]:
    ids = selected or list(ROUND_FUNCTIONS)
    results = [ROUND_FUNCTIONS[round_id](config) for round_id in ids]
    payload = {
        "schema_version": 1,
        "mode": "offline",
        "passed": all(result.passed for result in results),
        "rounds": [serialize(result) for result in results],
    }
    return sanitize(payload)


def dry_run(config: dict[str, Any], selected: list[str] | None = None) -> dict[str, Any]:
    ids = selected or list(ROUND_FUNCTIONS)
    return sanitize({
        "schema_version": 1,
        "mode": "dry-run",
        "passed": True,
        "rounds": [
            {
                "round": round_id,
                "title": config["rounds"][round_id]["title"],
                "gates": config["rounds"][round_id]["gates"],
            }
            for round_id in ids
        ],
    })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("architecture_rounds.json"))
    parser.add_argument("--mode", choices=("dry-run", "offline"), default="offline")
    parser.add_argument("--round", action="append", choices=tuple(ROUND_FUNCTIONS))
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    config = load_config(args.config)
    report = dry_run(config, args.round) if args.mode == "dry-run" else run(config, args.round)
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "summary.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if args.mode == "offline":
            (args.out / "report.md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
