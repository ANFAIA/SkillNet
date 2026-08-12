"""Offline screen-level screening for the currently emittable Didact boundary.

The fixture model intentionally replays one recorded response for every prompt.  This
bench therefore detects whether the current offline setup can discriminate prompt
selection arms; it must not be interpreted as model-quality evidence when it cannot.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import statistics
import sys
from tempfile import TemporaryDirectory
import time
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.llm.client import LLMConfig  # noqa: E402
from src.llm.fixtures import FixtureLLMService, write_fixture  # noqa: E402
from src.llm.prompts.runtime import build_ui_prompt  # noqa: E402
from src.personalization.didact_catalog import load_didact_catalog  # noqa: E402
from src.render.gate import canonicalize  # noqa: E402
from src.render.prompt_slice import BASE_SCOPE_COMPONENTS, build_didact_prompt_slice  # noqa: E402


BENCH_VERSION = "didact-screening/1"
ARMS = ("full-emittable", "facets-top5", "experience-intent-facets-top5")
FIXTURE_RESPONSE = Path(__file__).parents[1] / "src/llm/fixture_data/genera_ui/openui_explanation.txt"


def _emittable_ids() -> tuple[str, ...]:
    return tuple(item.type_id for item in load_didact_catalog().emittable)


def _ordered_shortlist(case: Mapping[str, Any], arm: str, allowed: tuple[str, ...]) -> tuple[str, ...]:
    """Rank only inside the audited emittable boundary.

    With five allowed entries and k=5 all arms necessarily contain the same set.  The
    order is retained for audit, while prompt slicing deliberately canonicalizes sets.
    """

    if arm == "full-emittable":
        return allowed
    preferred = tuple(map(str, case.get("oracle_shortlist" if arm.startswith("experience") else "facet_shortlist", [])))
    unknown = set(preferred) - set(allowed)
    if unknown:
        raise ValueError(f"shortlist crosses emittable boundary: {sorted(unknown)}")
    return tuple(dict.fromkeys((*preferred, *allowed)))[:5]


def _fact_proxy(spec: Mapping[str, Any], facts: list[Mapping[str, Any]]) -> float:
    payload = json.dumps(spec, ensure_ascii=False).lower()
    if not facts:
        return 1.0
    hits = sum(
        any(str(term).lower() in payload for term in fact.get("any_of", []))
        for fact in facts
    )
    return hits / len(facts)


def _preference_match(types: list[str], preference: str) -> float:
    presentations = {
        "TextContent": {"text"},
        "StepSequence": {"text"},
        "Callout": {"text"},
        "Flashcard": {"text"},
        "HintReveal": {"text"},
        "DidactGlossary": {"text"},
        "DidactTimeline": {"text"},
        "DidactWorkedExample": {"text"},
        "Chart": {"chart"},
    }
    content = [item for item in types if item != "Stack"]
    return (
        statistics.fmean(float(preference in presentations.get(item, set())) for item in content)
        if content
        else 0.0
    )


async def run_screening(raw: Mapping[str, Any]) -> dict[str, Any]:
    if raw.get("version") != BENCH_VERSION:
        raise ValueError(f"fixture version must be {BENCH_VERSION!r}")
    cases = list(raw.get("cases", []))
    if len(cases) != 5:
        raise ValueError("screening requires exactly five paired case/profile inputs")
    allowed = _emittable_ids()
    if len(allowed) != 5:
        raise ValueError(f"audited screening expected 5 emittable components, got {len(allowed)}")
    fixture_response = FIXTURE_RESPONSE.read_text(encoding="utf-8")
    rows: list[dict[str, Any]] = []
    with TemporaryDirectory(prefix="skillnet-didact-screen-") as directory:
        fixture_dir = Path(directory)
        llm = FixtureLLMService(
            LLMConfig(model="fixture/local", api_base=None, api_key=None),
            directory=fixture_dir,
        )
        for case in cases:
            user_prompt = build_ui_prompt(
                title=str(case["title"]),
                summary=str(case["summary"]),
                outcome=str(case["outcome"]),
                ui_format="explanation",
                effective_density=int(case["profile"]["density"]),
                role_title=str(case["profile"]["role"]),
                sector=str(case["profile"]["sector"]),
                experience_level=str(case["profile"]["experience"]),
                source_context=str(case["source"]),
                presentation_preference=str(case["profile"]["presentation"]),
            )
            for arm in ARMS:
                shortlist = _ordered_shortlist(case, arm, allowed)
                scope = build_didact_prompt_slice(shortlist)
                system_prompt = scope.prompt
                write_fixture(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response=fixture_response,
                    relative_path=f"responses/{case['id']}-{arm}.txt",
                    use_case="genera_ui",
                    directory=fixture_dir,
                )
                started = time.perf_counter()
                response = await llm.complete(
                    system_prompt, user_prompt, max_tokens=int(raw.get("max_tokens", 1200))
                )
                generation_ms = (time.perf_counter() - started) * 1000
                valid = True
                error = ""
                spec_dict: dict[str, Any] = {}
                try:
                    spec, _ = canonicalize(response, ui_format="explanation")
                    spec_dict = spec.model_dump(mode="json")
                except Exception as exc:  # noqa: BLE001 - validation failure is a metric
                    valid = False
                    error = f"{type(exc).__name__}: {exc}"
                types = [
                    str(item.get("type"))
                    for item in spec_dict.get("components", [])
                    if isinstance(item, Mapping) and item.get("type")
                ]
                emitted_content = set(types) - set(BASE_SCOPE_COMPONENTS)
                included = set(scope.included_component_ids)
                rows.append(
                    {
                        "case_id": case["id"],
                        "arm": arm,
                        "model": "fixture/local",
                        "shortlist": list(shortlist),
                        "included_components": list(scope.included_component_ids),
                        "ui_valid": valid,
                        "first_pass": valid,
                        "scope_compliant": emitted_content <= included,
                        "validation_error": error,
                        "types": types,
                        "semantic_signature": sorted(set(types) - set(BASE_SCOPE_COMPONENTS)),
                        "ui_sha256": sha256(response.encode()).hexdigest(),
                        "factual_proxy": _fact_proxy(spec_dict, list(case.get("critical_facts", []))),
                        "affordance_available": bool(emitted_content & included),
                        "evidence_available": False,
                        "preference_match": _preference_match(
                            types, str(case["profile"]["presentation"])
                        ),
                        "prompt_chars": len(system_prompt) + len(user_prompt),
                        "prompt_token_proxy": (len(system_prompt) + len(user_prompt) + 3) // 4,
                        "latency_ms": generation_ms,
                    }
                )

    summaries: dict[str, Any] = {}
    for arm in ARMS:
        selected = [row for row in rows if row["arm"] == arm]
        summaries[arm] = {
            "screens": len(selected),
            "ui_valid_rate": statistics.fmean(float(row["ui_valid"]) for row in selected),
            "first_pass_rate": statistics.fmean(float(row["first_pass"]) for row in selected),
            "scope_compliance_rate": statistics.fmean(
                float(row["scope_compliant"]) for row in selected
            ),
            "distinct_type_signatures": len(
                {tuple(row["semantic_signature"]) for row in selected}
            ),
            "mean_factual_proxy": statistics.fmean(row["factual_proxy"] for row in selected),
            "mean_preference_match": statistics.fmean(
                row["preference_match"] for row in selected
            ),
            "affordance_available_rate": statistics.fmean(
                float(row["affordance_available"]) for row in selected
            ),
            "evidence_available_rate": statistics.fmean(
                float(row["evidence_available"]) for row in selected
            ),
            "mean_prompt_chars": statistics.fmean(row["prompt_chars"] for row in selected),
            "mean_prompt_token_proxy": statistics.fmean(
                row["prompt_token_proxy"] for row in selected
            ),
            "median_latency_ms": statistics.median(row["latency_ms"] for row in selected),
        }
    prompt_hashes = {
        arm: {row["case_id"]: tuple(row["included_components"]) for row in rows if row["arm"] == arm}
        for arm in ARMS
    }
    outputs = {row["ui_sha256"] for row in rows}
    return {
        "bench_version": BENCH_VERSION,
        "fixture_id": raw.get("fixture_id"),
        "model": "fixture/local",
        "max_tokens": int(raw.get("max_tokens", 1200)),
        "emittable_ids": list(allowed),
        "arms": list(ARMS),
        "strict_emittable_gate": True,
        "identical_prompt_component_sets": len(
            {tuple(value) for arm_values in prompt_hashes.values() for value in arm_values.values()}
        ) == 1,
        "identical_fixture_outputs": len(outputs) == 1,
        "selector_discrimination_observable": False,
        "blocking_reason": (
            "top-k=5 equals the complete emittable boundary (5 components), and fixture/local "
            "replays one legacy StepSequence screen that does not obey the closed Didact scope"
        ),
        "summaries": summaries,
        "results": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline Didact screen screening")
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = asyncio.run(run_screening(json.loads(args.input.read_text(encoding="utf-8"))))
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
