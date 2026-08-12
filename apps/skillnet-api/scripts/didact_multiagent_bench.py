"""Offline simulation of capability-specialist selection over all 34 Didact types.

This is deliberately not wired to production.  It models five small agents (one per
``ProducerKind``) which all receive the same ExperienceIntent/knowledge-pack summary,
inspect their complete capability partition, and may propose or decline.  A typed,
blind arbiter sees proposal features but neither strategy names nor specialist names.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, replace
import json
from pathlib import Path
import statistics
import sys
from typing import Any, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.didact_selection_experiment import (  # noqa: E402
    ExperimentCase,
    _facet_scores,
    _metrics,
    eligible_catalog,
    load_manifest,
    rank_candidates,
)
from src.personalization.didact_descriptors import export_didact_descriptors  # noqa: E402
from src.personalization.plan import ComponentDescriptor, Presentation, ProducerKind  # noqa: E402


BENCH_VERSION = "didact-multiagent/1"
STRATEGIES = ("central-full", "specialists-blind", "specialists-expand")
SPECIALISTS = tuple(ProducerKind)
TOKENS_PER_DESCRIPTOR = 82
TOKENS_PER_PROPOSAL = 46
SHARED_INTENT_TOKENS = 180
DECLINE_THRESHOLD = 0.19


@dataclass(frozen=True, slots=True)
class Proposal:
    component: ComponentDescriptor
    relevance: float
    grounding: float
    port_feasibility: float
    richness: float
    preference_match: float


def _proposal(case: ExperimentCase, item: ComponentDescriptor) -> Proposal:
    facets = _facet_scores(case, item)
    grounding = statistics.fmean((facets["source"], facets["explicit_evidence"]))
    preference_match = facets["presentation"]
    richness = min(1.0, (len(item.affordances) + len(item.presentations)) / 6)
    return Proposal(
        component=item,
        relevance=facets["total"],
        grounding=grounding,
        port_feasibility=float(item.requirements <= case.objective.available_requirements),
        richness=richness,
        preference_match=preference_match,
    )


def _specialist_proposals(
    case: ExperimentCase,
    catalog: Sequence[ComponentDescriptor],
    *,
    limit: int,
) -> tuple[tuple[Proposal, ...], dict[str, str]]:
    """Let every capability specialist inspect its full partition and propose locally."""

    eligible_ids = {item.component_id for item in eligible_catalog(case, catalog)}
    proposals: list[Proposal] = []
    declines: dict[str, str] = {}
    for kind in SPECIALISTS:
        partition = tuple(item for item in catalog if item.producer_kind is kind)
        compatible = tuple(item for item in partition if item.component_id in eligible_ids)
        ranked = sorted(
            (_proposal(case, item) for item in compatible),
            key=lambda proposal: (-proposal.relevance, proposal.component.component_id),
        )
        if not ranked:
            declines[kind.value] = "no_hard_compatible_candidate"
        elif ranked[0].relevance < DECLINE_THRESHOLD:
            declines[kind.value] = "weak_intent_fit"
        else:
            proposals.extend(ranked[:limit])
    return tuple(proposals), declines


def _blind_arbitrate(proposals: Sequence[Proposal], *, limit: int = 5) -> tuple[ComponentDescriptor, ...]:
    """Aggregate typed features without receiving arm or specialist identity."""

    ranked = sorted(
        proposals,
        key=lambda proposal: (
            -(
                0.43 * proposal.relevance
                + 0.22 * proposal.grounding
                + 0.16 * proposal.richness
                + 0.12 * proposal.preference_match
                + 0.07 * proposal.port_feasibility
            ),
            proposal.component.component_id,
        ),
    )
    selected: list[ComponentDescriptor] = []
    producer_counts: Counter[ProducerKind] = Counter()
    for proposal in ranked:
        # Soft diversity: a second candidate from a family waits until three families
        # are represented.  This is not a component-name rule.
        kind = proposal.component.producer_kind
        if producer_counts[kind] and len(producer_counts) < min(3, len(SPECIALISTS)):
            continue
        selected.append(proposal.component)
        producer_counts[kind] += 1
        if len(selected) == limit:
            break
    if len(selected) < limit:
        selected_ids = {item.component_id for item in selected}
        selected.extend(
            proposal.component
            for proposal in ranked
            if proposal.component.component_id not in selected_ids
        )
    return tuple(selected[:limit])


def select(
    strategy: str,
    case: ExperimentCase,
    catalog: Sequence[ComponentDescriptor],
) -> tuple[tuple[ComponentDescriptor, ...], dict[str, str], int]:
    if strategy == "central-full":
        selected = rank_candidates("facets-mmr-k5", case, eligible_catalog(case, catalog))
        return selected, {}, SHARED_INTENT_TOKENS + len(catalog) * TOKENS_PER_DESCRIPTOR

    first_limit = 2 if strategy == "specialists-blind" else 1
    proposals, declines = _specialist_proposals(case, catalog, limit=first_limit)
    selected = _blind_arbitrate(proposals)
    proposal_count = len(proposals)
    if strategy == "specialists-expand" and (
        len(selected) < 3
        or statistics.fmean((_proposal(case, item).relevance for item in selected)) < 0.32
    ):
        proposals, declines = _specialist_proposals(case, catalog, limit=3)
        selected = _blind_arbitrate(proposals)
        proposal_count += len(proposals)
    # Parallel wall-context proxy is the largest partition, while total model work
    # still accounts for all five calls plus arbitration.
    total_tokens = (
        len(SPECIALISTS) * SHARED_INTENT_TOKENS
        + len(catalog) * TOKENS_PER_DESCRIPTOR
        + proposal_count * TOKENS_PER_PROPOSAL
    )
    return selected, declines, total_tokens


def _quality(case: ExperimentCase, selected: Sequence[ComponentDescriptor]) -> dict[str, float]:
    base = _metrics(case, selected)
    presentations = {value for item in selected for value in item.presentations}
    producer_kinds = {item.producer_kind for item in selected}
    richness = statistics.fmean(
        (
            base["affordance_coverage"],
            base["semantic_signature_diversity"],
            min(1.0, len(presentations) / 3),
            min(1.0, len(producer_kinds) / 3),
        )
    )
    grounding = statistics.fmean(
        (base["relevant_precision"], base["explicit_evidence_coverage"])
    )
    return {
        "richness": richness,
        "grounding_proxy": grounding,
        "port_feasibility": statistics.fmean(
            float(item.requirements <= case.objective.available_requirements) for item in selected
        )
        if selected
        else 0.0,
        "preference_match": base["preference_match"],
        "prohibited_rate": base["prohibited_rate"],
    }


def _profile_twin(case: ExperimentCase) -> ExperimentCase:
    current = tuple(case.projection.declared_presentations)
    alternative = (Presentation.IMAGE, Presentation.DIAGRAM)
    if set(current) & set(alternative):
        alternative = (Presentation.TEXT, Presentation.TABLE)
    return replace(case, projection=replace(case.projection, declared_presentations=alternative))


def run_experiment(raw: Mapping[str, Any]) -> dict[str, Any]:
    cases = load_manifest(raw)
    catalog = export_didact_descriptors()
    if len(catalog) != 34:
        raise ValueError(f"expected the complete 34-type Didact catalog, got {len(catalog)}")
    partitions = {
        kind.value: sorted(item.component_id for item in catalog if item.producer_kind is kind)
        for kind in SPECIALISTS
    }
    if set().union(*(set(values) for values in partitions.values())) != {
        item.component_id for item in catalog
    }:
        raise ValueError("specialist partitions do not cover the complete catalog")

    rows: list[dict[str, Any]] = []
    for strategy in STRATEGIES:
        for case in cases:
            selected, declines, tokens = select(strategy, case, catalog)
            twin_selected, _, _ = select(strategy, _profile_twin(case), catalog)
            selected_ids = [item.component_id for item in selected]
            twin_ids = [item.component_id for item in twin_selected]
            causal_change = 1 - len(set(selected_ids) & set(twin_ids)) / max(
                1, len(set(selected_ids) | set(twin_ids))
            )
            rows.append(
                {
                    "strategy": strategy,
                    "case_id": case.case_id,
                    "selected": selected_ids,
                    "profile_twin_selected": twin_ids,
                    "personalization_causal_change": causal_change,
                    "declines": declines,
                    "estimated_total_context_tokens": tokens,
                    "estimated_parallel_critical_context_tokens": (
                        tokens
                        if strategy == "central-full"
                        else SHARED_INTENT_TOKENS
                        + max(
                            sum(item.producer_kind is kind for item in catalog)
                            for kind in SPECIALISTS
                        )
                        * TOKENS_PER_DESCRIPTOR
                        + len(selected) * TOKENS_PER_PROPOSAL
                    ),
                    "metrics": _quality(case, selected),
                }
            )

    summaries: dict[str, Any] = {}
    for strategy in STRATEGIES:
        subset = [row for row in rows if row["strategy"] == strategy]
        summaries[strategy] = {
            "cases": len(subset),
            "mean_richness": statistics.fmean(row["metrics"]["richness"] for row in subset),
            "mean_grounding_proxy": statistics.fmean(
                row["metrics"]["grounding_proxy"] for row in subset
            ),
            "mean_port_feasibility": statistics.fmean(
                row["metrics"]["port_feasibility"] for row in subset
            ),
            "mean_personalization_causal_change": statistics.fmean(
                row["personalization_causal_change"] for row in subset
            ),
            "mean_estimated_total_context_tokens": statistics.fmean(
                row["estimated_total_context_tokens"] for row in subset
            ),
            "mean_estimated_parallel_critical_context_tokens": statistics.fmean(
                row["estimated_parallel_critical_context_tokens"] for row in subset
            ),
            "declines": sum(len(row["declines"]) for row in subset),
        }
    return {
        "bench_version": BENCH_VERSION,
        "fixture_id": raw.get("fixture_id"),
        "catalog_size": len(catalog),
        "catalog_coverage": 1.0,
        "specialist_partitions": partitions,
        "arbiter_blinding": [
            "component descriptor",
            "relevance",
            "grounding",
            "port feasibility",
            "richness",
            "preference match",
        ],
        "summaries": summaries,
        "results": rows,
        "limitations": [
            "Deterministic fixture proxy; it does not measure real LLM semantic quality.",
            "Grounding is a relevance/evidence proxy, not factual verification.",
            "Token counts are estimates and exclude provider-specific tokenization.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline multi-agent Didact experiment")
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = run_experiment(json.loads(args.input.read_text(encoding="utf-8")))
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
