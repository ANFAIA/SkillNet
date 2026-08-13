#!/usr/bin/env python
"""Paired, offline counterfactual audit of the on-the-fly personalization path.

The bench changes exactly one learner signal at a time while keeping node, source,
course, model key and repetition fixed.  It executes the same pure boundaries used by
the live runtime: profile projection, complete Didact planning, prompt construction and
render-cache key construction.  It intentionally does not pretend that ``fixture/local``
is evidence of LLM quality: the fixture has no generative semantics.  Its results prove
plumbing, deterministic selection and invalidation; a provider-backed run is still
required to judge prose and teaching quality.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from src.agents.runtime.shadow_plan import build_shadow_plan_trace
from src.llm.prompts.runtime import build_format_prompt, build_ui_prompt
from src.personalization.didact_catalog import load_didact_catalog
from src.personalization.preferences import normalize_learning_preferences
from src.services.node_render_service import build_render_key

BENCH_VERSION = "personalization-counterfactual/1"
MODEL_KEY = "fixture/local|fixture/local"
NODE_ID = uuid.UUID("850c6297-7a99-46ec-8712-cf03effcc8aa")
SOURCE_FACTS = (
    "La urgencia expresa cuanto puede esperar la incidencia.",
    "El impacto expresa a cuantas personas o servicios afecta.",
    "Impacto y urgencia determinan conjuntamente la prioridad.",
    "Una incidencia critica debe escalarse por el canal definido.",
)
SOURCE = "\n".join(SOURCE_FACTS)


@dataclass(frozen=True)
class ProfileCase:
    case_id: str
    changed_axis: str
    presentation: str = "balanced"
    detail: str = "standard"
    images: str = "when_useful"
    experience: str = "some"
    preset: str = "standard"
    accessibility: tuple[tuple[str, bool], ...] = ()
    format_vector: tuple[tuple[str, float], ...] = (
        ("texto", 0.7), ("ejercicio", 0.1), ("codigo", 0.0), ("dato", 0.2)
    )
    nodes_completed: int = 5
    scaffold_band: str = "neutral"

    def preferences(self) -> dict[str, Any]:
        return {
            "version": 1,
            "presentation": self.presentation,
            "detail": self.detail,
            "images": self.images,
        }


BASELINE = ProfileCase("baseline", "none")
CASES = (
    BASELINE,
    replace(BASELINE, case_id="presentation-visual", changed_axis="presentation", presentation="visual"),
    replace(BASELINE, case_id="presentation-textual", changed_axis="presentation", presentation="textual"),
    replace(BASELINE, case_id="presentation-interactive", changed_axis="presentation", presentation="interactive"),
    replace(BASELINE, case_id="detail-concise", changed_axis="detail", detail="concise"),
    replace(BASELINE, case_id="detail-detailed", changed_axis="detail", detail="detailed"),
    replace(BASELINE, case_id="images-prefer", changed_axis="images", images="prefer"),
    replace(BASELINE, case_id="images-avoid", changed_axis="images", images="avoid"),
    replace(BASELINE, case_id="experience-none", changed_axis="experience", experience="none"),
    replace(BASELINE, case_id="experience-experienced", changed_axis="experience", experience="experienced"),
    replace(BASELINE, case_id="accessibility-short-blocks", changed_axis="accessibility", accessibility=(("short_blocks", True),)),
    replace(BASELINE, case_id="accessibility-reduced-motion", changed_axis="accessibility", accessibility=(("reduce_motion", True),)),
    replace(BASELINE, case_id="vector-exercise-hot", changed_axis="format_vector", format_vector=(("texto", 0.1), ("ejercicio", 0.8), ("codigo", 0.0), ("dato", 0.1))),
    replace(BASELINE, case_id="vector-data-hot", changed_axis="format_vector", format_vector=(("texto", 0.1), ("ejercicio", 0.1), ("codigo", 0.0), ("dato", 0.8))),
    # Cold means the same stored vector exists but fewer than three completed nodes. The
    # production projection and cache intentionally suppress it during calibration.
    replace(BASELINE, case_id="vector-cold-calibration", changed_axis="format_vector_temperature", nodes_completed=0),
)


def _state(case: ProfileCase) -> tuple[dict[str, Any], Any, Any, dict[str, bool]]:
    accessibility = dict(case.accessibility)
    profile = SimpleNamespace(
        nodes_completed=case.nodes_completed,
        format_vector=dict(case.format_vector),
        role_title="Agente de soporte",
        sector="ticketing",
        preset=case.preset,
        experience_level=case.experience,
        learning_preferences=case.preferences(),
        personalization_revision=7,
    )
    course = SimpleNamespace(schema_version=4, intent_density=3)
    state = {
        "node_id": str(NODE_ID),
        "schema_version": 4,
        "node": {
            "id": str(NODE_ID),
            "title": "Priorizar y escalar una incidencia",
            "summary": "Decidir la prioridad con impacto y urgencia y aplicar el escalado.",
        },
        "profile": {
            "role_title": profile.role_title,
            "sector": profile.sector,
            "experience_level": profile.experience_level,
            "preset": profile.preset,
            "format_vector": profile.format_vector,
            "learning_preferences": profile.learning_preferences,
            "nodes_completed": profile.nodes_completed,
        },
        "accessibility": accessibility,
        "node_state": {"last_error_kind": None},
        "effective_density": 2 if accessibility.get("short_blocks") else 3,
        "scaffold_band": case.scaffold_band,
        "ui_format": "mixed",
        "shape_functions": ["contrastar", "evaluar"],
        "shape_summary": "reglas de decision y un procedimiento de escalado",
        "assessment_block": "QuizItem",
        "assessment_item_type": "test",
    }
    return state, profile, course, accessibility


def observe(case: ProfileCase) -> dict[str, Any]:
    started = time.perf_counter()
    state, profile, course, accessibility = _state(case)
    trace = build_shadow_plan_trace(state, mode="counterfactual-fixture")
    prefs = normalize_learning_preferences(case.preferences())
    key = build_render_key(
        node=SimpleNamespace(id=NODE_ID),
        course=course,
        profile=profile,
        node_state=SimpleNamespace(scaffold_band=case.scaffold_band),
        accessibility=accessibility,
        model_key=MODEL_KEY,
        backend="openui",
        knowledge_pack_key="pack-fixed:selection-fixed",
    )
    ui_prompt = build_ui_prompt(
        title=state["node"]["title"],
        summary=state["node"]["summary"],
        outcome="Priorizar correctamente y escalar cuando corresponda.",
        criticality="critical",
        ui_format="mixed",
        effective_density=key.effective_density,
        scaffold_band=case.scaffold_band,
        role_title=profile.role_title,
        sector=profile.sector,
        experience_level=case.experience,
        preset=case.preset,
        source_context=SOURCE,
        presentation_preference=prefs.presentation.value,
        detail_preference=prefs.detail.value,
        image_preference=prefs.images.value,
    )
    format_prompt = build_format_prompt(
        title=state["node"]["title"],
        summary=state["node"]["summary"],
        criticality="critical",
        default_ui_format="mixed",
        role_title=profile.role_title,
        sector=profile.sector,
        experience_level=case.experience,
        preset=case.preset,
        effective_density=key.effective_density,
        scaffold_band=case.scaffold_band,
        vector_bucket=key.vector_bucket,
        source_has_numbers=False,
        shape_summary=state["shape_summary"],
        presentation_preference=prefs.presentation.value,
        detail_preference=prefs.detail.value,
        image_preference=prefs.images.value,
    )
    shadow = trace.get("shadow") or {}
    candidates = shadow.get("component_candidates") or []
    signature = {
        "representations": shadow.get("representations") or [],
        "components": [item.get("component_id") for item in candidates],
        "affordances": sorted({value for item in candidates for value in item.get("affordances", [])}),
        "evidence": sorted({value for item in candidates for value in item.get("evidence_events", [])}),
        "support": shadow.get("support") or {},
        "prompt_components": trace.get("prompt_component_ids") or [],
    }
    elapsed = (time.perf_counter() - started) * 1000
    return {
        "case_id": case.case_id,
        "changed_axis": case.changed_axis,
        "cache_key": key.cache_key,
        "preference_bucket": key.preference_bucket,
        "accessibility_bucket": key.accessibility_bucket,
        "vector_bucket": key.vector_bucket,
        "calibrating": key.calibrating,
        "effective_density": key.effective_density,
        "personalization_revision": key.personalization_revision,
        "semantic_signature": signature,
        "critical_facts_in_prompt": [fact for fact in SOURCE_FACTS if fact in ui_prompt],
        "critical_fact_recall": sum(fact in ui_prompt for fact in SOURCE_FACTS) / len(SOURCE_FACTS),
        "prompt_changed_material": f"{format_prompt}\n{ui_prompt}",
        "prompt_chars": len(format_prompt) + len(ui_prompt),
        "estimated_prompt_tokens": round((len(format_prompt) + len(ui_prompt)) / 4),
        "measured_pipeline_ms": round(elapsed, 3),
        "tokens_reported_by_fixture": None,
        "cost_reported_by_fixture": None,
        "trace_status": trace.get("status"),
        "inventory_size_with_legacy": trace.get("inventory_size"),
    }


def _semantic_delta(base: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
    left, right = base["semantic_signature"], variant["semantic_signature"]
    fields = ("representations", "components", "affordances", "evidence", "support", "prompt_components")
    changed = [field for field in fields if left[field] != right[field]]
    return {
        "semantic_fields_changed": changed,
        "useful_semantic_change": bool(changed),
        "cache_invalidated": base["cache_key"] != variant["cache_key"],
        "prompt_changed": base["prompt_changed_material"] != variant["prompt_changed_material"],
    }


def run(*, repetitions: int = 5) -> dict[str, Any]:
    catalog = load_didact_catalog()
    observations: dict[str, list[dict[str, Any]]] = {
        case.case_id: [observe(case) for _ in range(repetitions)] for case in CASES
    }
    baseline = observations[BASELINE.case_id][0]
    rows: list[dict[str, Any]] = []
    for case in CASES[1:]:
        first = observations[case.case_id][0]
        repeat_signatures = {
            json.dumps(item["semantic_signature"], sort_keys=True)
            for item in observations[case.case_id]
        }
        rows.append(
            {
                **{key: value for key, value in first.items() if key != "prompt_changed_material"},
                **_semantic_delta(baseline, first),
                "intraprofile_semantic_noise": len(repeat_signatures) - 1,
                "mean_pipeline_ms": round(statistics.fmean(item["measured_pipeline_ms"] for item in observations[case.case_id]), 3),
            }
        )
    return {
        "bench_version": BENCH_VERSION,
        "claim_boundary": {
            "proves": "runtime signal plumbing, planner response, prompt propagation, cache invalidation, calibration suppression and deterministic repetition",
            "does_not_prove": "LLM prose quality, learning gain, provider latency, provider tokens or monetary cost",
            "model": MODEL_KEY,
        },
        "fixed_input": {"node_id": str(NODE_ID), "source_facts": list(SOURCE_FACTS), "schema_version": 4},
        "didact_universe": {
            "count": len(catalog.components),
            "type_ids": [item.type_id for item in catalog.components],
            "complete": len(catalog.components) == 34,
        },
        "repetitions": repetitions,
        "baseline": {key: value for key, value in baseline.items() if key != "prompt_changed_material"},
        "counterfactuals": rows,
        "summary": {
            "pairs": len(rows),
            "prompt_change_rate": round(statistics.fmean(float(row["prompt_changed"]) for row in rows), 3),
            "cache_invalidation_rate": round(statistics.fmean(float(row["cache_invalidated"]) for row in rows), 3),
            "useful_semantic_change_rate": round(statistics.fmean(float(row["useful_semantic_change"]) for row in rows), 3),
            "critical_fact_recall": round(statistics.fmean(row["critical_fact_recall"] for row in rows), 3),
            "intraprofile_noise_cases": sum(bool(row["intraprofile_semantic_noise"]) for row in rows),
            "semantic_change_without_cache_invalidation": [
                row["case_id"]
                for row in rows
                if row["useful_semantic_change"] and not row["cache_invalidated"]
            ],
            "prompt_only_axes": [
                row["case_id"]
                for row in rows
                if row["prompt_changed"] and not row["useful_semantic_change"]
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = run(repetitions=args.repetitions)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
