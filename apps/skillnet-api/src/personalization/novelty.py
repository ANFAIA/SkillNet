"""Offline-only ranking diagnostics and bounded useful-novelty tie breaking.

Nothing imports this module from the runtime. Novelty may reorder candidates only inside
an equivalence class that already passed mission, requirements, preferences, accessibility
and grounding/evidence checks. It cannot make an ineligible component eligible.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence, TypeVar

from src.personalization.plan import ComponentCandidate

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RankingCollapse:
    samples: int
    unique_top_components: int
    dominant_component: str | None
    dominant_share: float
    normalized_entropy: float
    collapsed: bool


def ranking_collapse(
    rankings: Iterable[Sequence[ComponentCandidate]], *, dominant_threshold: float = 0.70
) -> RankingCollapse:
    tops = [ranking[0].component_id for ranking in rankings if ranking]
    counts = Counter(tops)
    if not tops:
        return RankingCollapse(0, 0, None, 0.0, 0.0, False)
    dominant, count = counts.most_common(1)[0]
    share = count / len(tops)
    if len(counts) == 1:
        entropy = 0.0
    else:
        raw = -sum((value / len(tops)) * math.log(value / len(tops)) for value in counts.values())
        entropy = raw / math.log(len(counts))
    return RankingCollapse(
        samples=len(tops),
        unique_top_components=len(counts),
        dominant_component=dominant,
        dominant_share=round(share, 4),
        normalized_entropy=round(entropy, 4),
        collapsed=share >= dominant_threshold and len(tops) >= 5,
    )


def _equivalence_key(candidate: ComponentCandidate) -> tuple[object, ...]:
    """Information that novelty is forbidden to overrule."""

    return (
        candidate.rank,
        candidate.version,
        candidate.presentation,
        candidate.producer_kind,
        tuple(sorted(candidate.affordances)),
        tuple(sorted(candidate.evidence_events)),
        candidate.state_model_ref,
    )


def useful_novelty_tiebreak(
    candidates: Sequence[ComponentCandidate],
    *,
    prior_exposure: Mapping[str, int],
    semantic_family: Mapping[str, str] | None = None,
) -> tuple[ComponentCandidate, ...]:
    """Prefer a less-repeated equivalent candidate, never a lower-quality one.

    Stable equivalence groups preserve every upstream filter and rank boundary. Within a
    group, lower component exposure wins; then lower family exposure; original order is
    the final tie break. ``semantic_family`` is experimental metadata, not a runtime rule.
    """

    families = semantic_family or {}
    family_exposure = Counter()
    for component_id, count in prior_exposure.items():
        family_exposure[families.get(component_id, component_id)] += max(0, int(count))

    output: list[ComponentCandidate] = []
    start = 0
    while start < len(candidates):
        key = _equivalence_key(candidates[start])
        end = start + 1
        while end < len(candidates) and _equivalence_key(candidates[end]) == key:
            end += 1
        group = list(enumerate(candidates[start:end], start=start))
        group.sort(
            key=lambda pair: (
                max(0, int(prior_exposure.get(pair[1].component_id, 0))),
                family_exposure[families.get(pair[1].component_id, pair[1].component_id)],
                pair[0],
            )
        )
        output.extend(candidate for _, candidate in group)
        start = end
    return tuple(output)


__all__ = ["RankingCollapse", "ranking_collapse", "useful_novelty_tiebreak"]
