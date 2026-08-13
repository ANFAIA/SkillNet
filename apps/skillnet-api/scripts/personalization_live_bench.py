#!/usr/bin/env python
"""Counterfactual, on-the-fly personalization evaluation over the real runtime graph.

No provider is contacted unless ``--online`` is explicit.  The default fixture run is a
contract test for the harness; it is not evidence that a model personalizes well.
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import hashlib
import json
import random
import statistics
import sys
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:  # noqa: E402 - script works both as a file and as ``scripts.*`` in pytest.
    import quality_bench as qb
except ModuleNotFoundError:  # pragma: no cover - exercised by the test import path.
    from scripts import quality_bench as qb
from src.agents.runtime.selection_eval import EfficiencyMetrics  # noqa: E402
from src.config import settings  # noqa: E402
from src.core import sse  # noqa: E402
from src.personalization.didact_catalog import load_didact_catalog  # noqa: E402
from src.personalization.selection_policy import (  # noqa: E402
    SelectionExecution,
    SelectionPolicyError,
    SelectionStrategy,
    runtime_execution,
)

FORMAT_VERSION = "personalization-live-bench/3"


@dataclass(frozen=True, slots=True)
class CounterfactualProfile:
    id: str
    role_title: str
    experience_level: str
    preset: str
    nodes_completed: int
    intent_density: int
    scaffold_band: str
    short_blocks: bool
    consecutive_correct: int = 0
    consecutive_failed: int = 0
    last_error_kind: str | None = None
    tutor_signals: tuple[str, ...] = ()


PROFILES = (
    CounterfactualProfile(
        "novice_guided", "persona nueva en el puesto", "none", "focus", 0, 2,
        "high", True, consecutive_failed=2, last_error_kind="conceptual",
        tutor_signals=("reforzar_con_ejemplo",),
    ),
    CounterfactualProfile(
        "practitioner", "profesional que ejecuta el procedimiento", "some",
        "standard", 12, 3, "neutral", False,
    ),
    CounterfactualProfile(
        "expert_fast", "responsable con experiencia que revisa excepciones", "experienced",
        "fast", 40, 4, "low", False, consecutive_correct=4,
    ),
)


def _case(base: qb.Encargo, profile: CounterfactualProfile) -> qb.Encargo:
    return replace(
        base,
        name=f"{base.name}--{profile.id}",
        role_title=profile.role_title,
        experience_level=profile.experience_level,
        preset=profile.preset,
        nodes_completed=profile.nodes_completed,
        intent_density=profile.intent_density,
        scaffold_band=profile.scaffold_band,
        short_blocks=profile.short_blocks,
        consecutive_correct=profile.consecutive_correct,
        consecutive_failed=profile.consecutive_failed,
        last_error_kind=profile.last_error_kind,
        tutor_signals=profile.tutor_signals,
        offline_bad_attempts=0,
    )


def _didact_ids(run: qb.RunResult) -> tuple[str, ...]:
    trace = run.plan_trace or {}
    selection = trace.get("selection") if isinstance(trace, dict) else None
    policy_trace = (
        selection.get("policy_trace") if isinstance(selection, dict) else None
    )
    if (
        isinstance(policy_trace, dict)
        and selection.get("effective_execution") == SelectionExecution.LIVE.value
    ):
        return tuple(
            str(candidate_id)
            for candidate_id in policy_trace.get("selected_ids") or ()
            if str(candidate_id).startswith("didact.")
        )
    shadow = trace.get("shadow") if isinstance(trace, dict) else None
    candidates = shadow.get("component_candidates") if isinstance(shadow, dict) else ()
    return tuple(
        str(item["component_id"])
        for item in candidates or ()
        if isinstance(item, dict) and str(item.get("component_id", "")).startswith("didact.")
    )


_LEARNER_ACTION_COMPONENTS = frozenset(
    {
        "QuizItem",
        "DragOrder",
        "PronunciationExercise",
        "Flashcard",
        "HintReveal",
        "DidactGlossary",
        "DidactTimeline",
        "DidactWorkedExample",
        "DidactActivity",
    }
)
_EVIDENCE_EVENT_BY_COMPONENT = {
    "QuizItem": "answer_submitted",
    "DragOrder": "order_submitted",
    "PronunciationExercise": "pronunciation_attempted",
    "Flashcard": "recall_revealed",
    "HintReveal": "hint_requested",
    "DidactGlossary": "term_inspected",
    "DidactTimeline": "step_inspected",
    "DidactWorkedExample": "worked_step_revealed",
    "DidactActivity": "activity_interacted",
}


def _served_components(run: qb.RunResult) -> list[dict[str, Any]]:
    components = (run.ui_spec or {}).get("components")
    return [item for item in components or () if isinstance(item, dict)]


def _signature(run: qb.RunResult) -> tuple[Any, ...]:
    """Useful observable adaptation; no prose, callouts, layout or child order."""

    activity = run.authored_activity or {}
    public_definition = activity.get("public_definition") if isinstance(activity, dict) else None
    canonical_activity = json.dumps(
        public_definition or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    action_types = sorted(
        str(item.get("type"))
        for item in _served_components(run)
        if item.get("type") in _LEARNER_ACTION_COMPONENTS
    )
    evidence_events = sorted(
        {_EVIDENCE_EVENT_BY_COMPONENT[item] for item in action_types}
    )
    support_policy = sorted(
        value
        for value, present in (
            ("graduated_hints", "HintReveal" in action_types),
            ("worked_example", "DidactWorkedExample" in action_types),
            (
                "direct_feedback",
                bool({"QuizItem", "DragOrder", "DidactActivity"} & set(action_types)),
            ),
        )
        if present
    )
    return (
        tuple(action_types),
        tuple(evidence_events),
        tuple(support_policy),
        len(action_types),
        activity.get("component_id") if isinstance(activity, dict) else None,
        canonical_activity,
    )


def _superficial_signature(run: qb.RunResult) -> str:
    """Any canonical UI change, reported separately and never used for promotion."""

    return json.dumps(
        run.ui_spec or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _mean_pairwise_jaccard(values: list[tuple[str, ...]]) -> float:
    pairs: list[float] = []
    for index, left in enumerate(values):
        for right in values[index + 1 :]:
            a, b = set(left), set(right)
            pairs.append(len(a & b) / len(a | b) if a | b else 1.0)
    return statistics.fmean(pairs) if pairs else 1.0


def _prompt_payload(recorder: qb.Recorder) -> dict[str, Any]:
    return {
        "activity_authoring": {
            "system": recorder.activity_system_prompt,
            "user": recorder.activity_user_prompt,
        },
        "generation_attempts": [
            {
                "index": attempt.index,
                "system": attempt.system_prompt,
                "user": attempt.user_prompt,
                "raw_response": attempt.raw_dsl,
                "validation_errors": attempt.errors,
            }
            for attempt in recorder.attempts
        ],
    }


def _install_grounded_source_refs() -> None:
    """Give the in-memory DB seam stable refs equivalent to a ready source snapshot.

    ``quality_bench.BenchSession`` deliberately has no PostgreSQL knowledge-pack row.
    Activity authoring is stricter than legacy OpenUI and refuses uncited definitions, so
    this bench derives opaque refs from the exact recovered source.  It changes neither
    the source text nor the runtime authoring/validation path.
    """

    original = qb._replace_bench_context

    def replace_context(result: dict[str, Any], recorder: qb.Recorder) -> dict[str, Any]:
        replaced = original(result, recorder)
        source = str(result.get("source_context") or "")
        pack = qb.KnowledgePack.from_source(source)
        selected = pack.select(profile=result.get("profile"))
        return {
            **replaced,
            "knowledge_pack_hash": pack.source_digest,
            "knowledge_atom_ids": list(selected.atom_ids),
            "knowledge_evidence_ids": [],
        }

    qb._replace_bench_context = replace_context


def _blind_packet(rows: list[dict[str, Any]], seed: int) -> dict[str, Any]:
    shuffled = list(rows)
    random.Random(seed).shuffle(shuffled)
    items = []
    key: dict[str, Any] = {}
    for index, row in enumerate(shuffled, 1):
        blind_id = f"R{index:04d}"
        key[blind_id] = {
            "case": row["case"], "profile": row["profile"], "repeat": row["repeat"]
        }
        items.append(
            {
                "blind_id": blind_id,
                "objective": row["objective"],
                "source": row["source"],
                "ui_spec": row["run"]["ui_spec"],
                "activity_definition": row["run"]["authored_activity"],
                "rubric": {
                    "grounding_1_5": None,
                    "pedagogical_fit_1_5": None,
                    "useful_adaptation_1_5": None,
                    "interaction_richness_1_5": None,
                    "notes": "",
                },
            }
        )
    return {"items": items, "answer_key": key}


def _audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    catalog = load_didact_catalog()
    inventory = tuple(item.type_id for item in catalog.components)
    observed = {item for row in rows for item in row["didact_candidates"]}
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((row["case"], row["profile"]), []).append(row)

    stability = statistics.fmean(
        _mean_pairwise_jaccard([tuple(item["didact_candidates"][:5]) for item in values])
        for values in grouped.values()
    )
    scenario_profile_signatures: dict[str, dict[str, set[str]]] = {}
    scenario_profile_superficial: dict[str, dict[str, set[str]]] = {}
    for row in rows:
        scenario_profile_signatures.setdefault(row["case"], {}).setdefault(
            row["profile"], set()
        ).add(row["semantic_signature"])
        scenario_profile_superficial.setdefault(row["case"], {}).setdefault(
            row["profile"], set()
        ).add(row["superficial_signature"])
    changed = 0
    for profiles in scenario_profile_signatures.values():
        representatives = [sorted(values)[0] for values in profiles.values()]
        changed += int(len(set(representatives)) > 1)
    causal_change = changed / len(scenario_profile_signatures) if scenario_profile_signatures else 0
    superficial_changed = 0
    for profiles in scenario_profile_superficial.values():
        representatives = [sorted(values)[0] for values in profiles.values()]
        superficial_changed += int(len(set(representatives)) > 1)
    superficial_change = (
        superficial_changed / len(scenario_profile_superficial)
        if scenario_profile_superficial
        else 0
    )
    graded = [row for row in rows if row["run"]["outcome"] != "infra_error"]
    fallback_rate = (
        sum(row["run"]["outcome"] == "fallback" for row in graded) / len(graded)
        if graded
        else 1.0
    )
    candidate_tops = [
        row["didact_candidates"][0] for row in rows if row["didact_candidates"]
    ]
    top_counts = collections.Counter(candidate_tops)
    dominant_top, dominant_count = top_counts.most_common(1)[0] if top_counts else (None, 0)
    dominant_share = dominant_count / len(candidate_tops) if candidate_tops else 0.0
    requested_activities = [
        row
        for row in rows
        if row["run"].get("activity_authoring_status")
        not in {None, "not_observed", "not_requested"}
    ]
    materialized_activities = [
        row for row in requested_activities if row["run"].get("authored_activity")
    ]
    materialization_rate = (
        len(materialized_activities) / len(requested_activities)
        if requested_activities
        else None
    )

    source_invariance = all(
        len({row["run"]["source_digest"] for row in rows if row["case"] == case}) == 1
        for case in {row["case"] for row in rows}
    )
    gates = {
        "catalog_exactly_34": len(inventory) == 34 and len(set(inventory)) == 34,
        "all_candidates_in_catalog": observed <= set(inventory),
        "source_invariant_across_profiles": source_invariance,
        "no_infrastructure_errors": all(row["run"]["outcome"] != "infra_error" for row in rows),
        "valid_ui_or_honest_fallback": all(row["run"]["ui_spec"] is not None for row in rows),
        "intra_profile_stability_gte_0_50": stability >= 0.50,
        "useful_counterfactual_change_gte_0_50": causal_change >= 0.50,
        "fallback_rate_lte_0_10": fallback_rate <= 0.10,
        "activity_materialization_gte_0_50_when_requested": (
            materialization_rate is None or materialization_rate >= 0.50
        ),
    }
    return {
        "gates": gates,
        "promotable": all(gates.values()),
        "metrics": {
            "intra_profile_candidate_stability": round(stability, 4),
            "useful_counterfactual_causal_change_rate": round(causal_change, 4),
            "superficial_change_rate": round(superficial_change, 4),
            "fallback_rate": round(fallback_rate, 4),
            "activity_authoring_requested": len(requested_activities),
            "activity_materialized": len(materialized_activities),
            "activity_materialization_rate": (
                round(materialization_rate, 4) if materialization_rate is not None else None
            ),
            "ranking_unique_top_components": len(top_counts),
            "ranking_dominant_component": dominant_top,
            "ranking_dominant_share": round(dominant_share, 4),
            "ranking_collapsed": len(candidate_tops) >= 5 and dominant_share >= 0.70,
            "didact_inventory_count": len(inventory),
            "didact_observed_count": len(observed),
        },
        "didact_inventory": [
            {
                "type_id": item.type_id,
                "availability": item.availability_status.value,
                "emission": item.emission_status.value,
                "renderer": item.renderer_symbol,
                "observed_as_candidate": item.type_id in observed,
            }
            for item in catalog.components
        ],
    }


def _strategy_arg(value: str) -> SelectionStrategy:
    try:
        return SelectionStrategy.parse(value)
    except SelectionPolicyError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _selection_preflight(strategy: SelectionStrategy | str) -> dict[str, Any]:
    requested = SelectionStrategy.parse(strategy)
    effective = runtime_execution(SelectionExecution.LIVE, requested)
    return {
        "requested_strategy": requested.value,
        "requested_execution": SelectionExecution.LIVE.value,
        "effective_execution": effective.value,
        "executed_strategy": (
            requested.value if effective is SelectionExecution.LIVE else None
        ),
        "selection_contract_connected": True,
        "claim_boundary": (
            "Observed execution is read from each runtime plan trace. Strategies requiring "
            "an independent ranking remain shadow-only."
        ),
    }


def _selection_observation(run: qb.RunResult) -> dict[str, Any]:
    trace = run.plan_trace or {}
    selection = trace.get("selection") if isinstance(trace, dict) else None
    if not isinstance(selection, dict):
        return {
            "requested_strategy": None,
            "requested_execution": None,
            "effective_execution": None,
            "executed_strategy": None,
            "status": "not_observed",
        }
    return {
        key: selection.get(key)
        for key in (
            "requested_strategy",
            "requested_execution",
            "effective_execution",
            "executed_strategy",
            "status",
        )
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--online",
        action="store_true",
        help="Autoriza llamadas al proveedor configurado.",
    )
    result.add_argument("--model", help="Modelo pequeno real para fast y heavy.")
    result.add_argument(
        "--strategy",
        type=_strategy_arg,
        default=SelectionStrategy.TOP5,
        metavar="ID",
        help="Versioned selection contract executed by the runtime when live-capable.",
    )
    result.add_argument("--repeat", type=int, default=3)
    result.add_argument("--only", action="append", default=[])
    result.add_argument("--out", type=Path, default=ROOT / "bench_out" / "personalization")
    result.add_argument("--seed", type=int, default=20260812)
    result.add_argument("--price-in", type=float)
    result.add_argument("--price-out", type=float)
    result.add_argument(
        "--plan", action="store_true", help="Solo calcula renders y coste supuesto."
    )
    result.add_argument("--assumed-input-tokens", type=int, default=5000)
    result.add_argument("--assumed-output-tokens", type=int, default=1500)
    return result


async def run(args: argparse.Namespace) -> int:
    preflight = _selection_preflight(args.strategy)
    settings.RUNTIME_COMPONENT_SHORTLIST = True
    settings.RUNTIME_SELECTION_STRATEGY = args.strategy
    settings.RUNTIME_SELECTION_EXECUTION = SelectionExecution.LIVE
    corpus = qb.select_corpus(args.only)
    renders = len(corpus) * len(PROFILES) * args.repeat
    model = args.model or ("fixture/bench" if not args.online else settings.LLM_RUNTIME_FAST_MODEL)
    prices = qb.resolve_prices(args)
    tariff = prices.get(model)
    estimate = None
    if tariff:
        estimate = renders * (
            args.assumed_input_tokens / 1e6 * tariff[0]
            + args.assumed_output_tokens / 1e6 * tariff[1]
        )
    print(f"{len(corpus)} casos x {len(PROFILES)} perfiles x {args.repeat} = {renders} renders")
    print(f"Coste supuesto: {'n/d' if estimate is None else f'USD {estimate:.4f}'}")
    print(json.dumps({"selection_preflight": preflight}, ensure_ascii=False))
    if args.plan:
        return 0
    if args.repeat < 2:
        raise SystemExit("--repeat debe ser >=2 para medir estabilidad intraperfil")
    if args.online and not settings.LLM_API_KEY:
        raise SystemExit("--online requiere LLM_API_KEY")

    collector = qb.SseCollector()
    sse.publish = collector.publish  # type: ignore[assignment]
    sse.wait_for_subscriber = collector.wait_for_subscriber  # type: ignore[assignment]
    if args.online:
        if args.model:
            settings.LLM_RUNTIME_FAST_MODEL = args.model
            settings.LLM_RUNTIME_HEAVY_MODEL = args.model
        qb.install_provider_shim(qb.ProviderStats(), user_agent=qb.BENCH_USER_AGENT)
        qb.install_prompt_capture()
    else:
        settings.LLM_MODEL = qb.OFFLINE_MODEL
        settings.LLM_RUNTIME_FAST_MODEL = qb.OFFLINE_MODEL
        settings.LLM_RUNTIME_HEAVY_MODEL = qb.OFFLINE_MODEL
        settings.EMBEDDING_MODEL = qb.OFFLINE_MODEL
        qb.install_offline_llm(args.out / "fixtures")
        qb.install_offline_prompt_capture()
    qb.install_node_instrumentation()
    _install_grounded_source_refs()

    rows: list[dict[str, Any]] = []
    for base in corpus:
        for profile in PROFILES:
            case = _case(base, profile)
            for repeat_index in range(1, args.repeat + 1):
                result, recorder = await qb.run_one(
                    case, repeat_index, offline=not args.online, prices=prices
                )
                result.encargo = base.name
                payload = asdict(result)
                selection_observation = _selection_observation(result)
                signature = hashlib.sha256(
                    json.dumps(_signature(result), sort_keys=True, default=str).encode()
                ).hexdigest()
                superficial_signature = hashlib.sha256(
                    _superficial_signature(result).encode()
                ).hexdigest()
                rows.append(
                    {
                        "case": base.name,
                        "profile": profile.id,
                        **selection_observation,
                        "profile_inputs": asdict(profile),
                        "repeat": repeat_index,
                        "objective": base.outcome,
                        "source": base.source_text,
                        "run": payload,
                        "prompts": _prompt_payload(recorder),
                        "didact_candidates": list(_didact_ids(result)),
                        "semantic_signature": signature,
                        "superficial_signature": superficial_signature,
                        "efficiency": asdict(
                            EfficiencyMetrics(
                                latency_ms=round(result.seconds * 1000),
                                tokens_in=result.tokens_in,
                                tokens_out=result.tokens_out,
                                cost_usd=result.cost_usd,
                                attempts=result.attempts,
                            )
                        ),
                    }
                )

    audit = _audit(rows)
    audit["automatic_gates_passed"] = bool(audit.pop("promotable"))
    # Fixtures validate plumbing only.  Treating deterministic replay as product evidence
    # would let a scripted response "win" the experiment it was written to exercise.
    audit["promotable"] = bool(args.online and audit["automatic_gates_passed"])
    audit["promotion_blocker"] = (
        None if args.online else "offline fixtures are not model-quality evidence"
    )
    blind = _blind_packet(rows, args.seed)
    observed_executed = sorted(
        {
            str(row["executed_strategy"])
            for row in rows
            if row.get("executed_strategy")
        }
    )
    started = datetime.now(timezone.utc)
    args.out.mkdir(parents=True, exist_ok=True)
    stem = f"personalization-{started.strftime('%Y%m%d-%H%M%S')}"
    report = {
        "format": FORMAT_VERSION,
        "created_at": started.isoformat(),
        "mode": "online" if args.online else "offline-fixture",
        "model": model,
        "requested_strategy": preflight["requested_strategy"],
        "executed_strategy": (
            observed_executed[0] if len(observed_executed) == 1 else None
        ),
        "observed_executed_strategies": observed_executed,
        "selection_preflight": preflight,
        "render_count": renders,
        "profiles": [asdict(profile) for profile in PROFILES],
        "audit": audit,
        "runs": rows,
    }
    (args.out / f"{stem}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.out / f"{stem}-blind.json").write_text(
        json.dumps(blind, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    if not args.online:
        harness_gates = (
            "catalog_exactly_34",
            "all_candidates_in_catalog",
            "source_invariant_across_profiles",
            "no_infrastructure_errors",
            "valid_ui_or_honest_fallback",
        )
        return 0 if all(audit["gates"][gate] for gate in harness_gates) else 1
    return 0 if audit["promotable"] else 1


def main() -> int:
    return asyncio.run(run(parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
