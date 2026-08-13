"""Pure, deterministic selection policies for experiments and future runtime adapters.

The contract intentionally has no dependency on the runtime graph or an LLM. Callers must
provide every ranking and portfolio label used by a policy. Invalid or incomplete requests
raise ``SelectionPolicyError`` instead of silently falling back to another strategy.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable


CONTRACT_VERSION = "selection-policy/1"


class SelectionPolicyError(ValueError):
    """A selection request is unknown, malformed, or lacks required policy inputs."""


class SelectionExecution(StrEnum):
    OFF = "off"
    SHADOW = "shadow"
    LIVE = "live"

    @classmethod
    def parse(cls, value: str | SelectionExecution) -> SelectionExecution:
        if isinstance(value, cls):
            return value
        try:
            return cls(value)
        except ValueError as exc:
            known = ", ".join(item.value for item in cls)
            raise SelectionPolicyError(
                f"unknown selection execution {value!r}; expected: {known}"
            ) from exc


class SelectionStrategy(StrEnum):
    TOP5 = "top5/v1"
    PORTFOLIO_BALANCED_5 = "portfolio-balanced-5/v1"
    PORTFOLIO_EXPLORATORY_8 = "portfolio-exploratory-8/v1"
    PROGRESSIVE_3_5_CATALOG = "progressive-3-5-catalog/v1"
    DUAL_AGENT = "dual-agent/v1"
    CONDITIONAL_SPECIALIST = "conditional-specialist/v1"
    FULL_CATALOG_CONTROL = "full-catalog-control/v1"

    @classmethod
    def parse(cls, value: str | SelectionStrategy) -> SelectionStrategy:
        if isinstance(value, cls):
            return value
        try:
            return cls(value)
        except ValueError as exc:
            known = ", ".join(item.value for item in cls)
            raise SelectionPolicyError(f"unknown selection strategy {value!r}; expected: {known}") from exc


# These policies need an independently-produced ranking that the runtime does not have.
# They remain valid pure contracts for experiments, but must not be presented as live.
RUNTIME_SHADOW_ONLY_STRATEGIES = frozenset(
    {
        SelectionStrategy.DUAL_AGENT,
        SelectionStrategy.CONDITIONAL_SPECIALIST,
    }
)


def runtime_execution(
    execution: str | SelectionExecution,
    strategy: str | SelectionStrategy,
) -> SelectionExecution:
    """Return the honest runtime execution mode for the available producers."""

    parsed_execution = SelectionExecution.parse(execution)
    parsed_strategy = SelectionStrategy.parse(strategy)
    if (
        parsed_execution is SelectionExecution.LIVE
        and parsed_strategy in RUNTIME_SHADOW_ONLY_STRATEGIES
    ):
        return SelectionExecution.SHADOW
    return parsed_execution


def live_cache_fragment(
    execution: str | SelectionExecution,
    strategy: str | SelectionStrategy,
) -> str:
    """Version the shared render cache only when a policy can affect live output."""

    effective = runtime_execution(execution, strategy)
    if effective is not SelectionExecution.LIVE:
        return ""
    return f"{CONTRACT_VERSION}:{SelectionStrategy.parse(strategy).value}"


class ProgressiveStage(StrEnum):
    TOP3 = "top3"
    TOP5 = "top5"
    CATALOG = "catalog"


@dataclass(frozen=True, slots=True)
class SelectionCandidate:
    candidate_id: str
    portfolio: str = "default"


@dataclass(frozen=True, slots=True)
class SelectionRequest:
    strategy: SelectionStrategy
    candidates: tuple[SelectionCandidate, ...]
    secondary_ranking: tuple[str, ...] = ()
    specialist_ranking: tuple[str, ...] = ()
    progressive_stage: ProgressiveStage = ProgressiveStage.TOP3
    activate_specialist: bool = False


@dataclass(frozen=True, slots=True)
class SelectionTrace:
    contract_version: str
    requested_strategy: SelectionStrategy
    executed_strategy: SelectionStrategy
    stage: str
    considered_ids: tuple[str, ...]
    selected_ids: tuple[str, ...]
    decision_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SelectionResult:
    selected_ids: tuple[str, ...]
    trace: SelectionTrace


def _validate(request: SelectionRequest) -> None:
    SelectionStrategy.parse(request.strategy)
    try:
        ProgressiveStage(request.progressive_stage)
    except ValueError as exc:
        known = ", ".join(item.value for item in ProgressiveStage)
        raise SelectionPolicyError(
            f"unknown progressive stage {request.progressive_stage!r}; expected: {known}"
        ) from exc
    if not request.candidates:
        raise SelectionPolicyError("selection requires at least one candidate")
    ids = tuple(item.candidate_id for item in request.candidates)
    if any(not candidate_id.strip() for candidate_id in ids):
        raise SelectionPolicyError("candidate ids must be non-empty")
    if len(ids) != len(set(ids)):
        raise SelectionPolicyError("candidate ids must be unique")
    if any(not item.portfolio.strip() for item in request.candidates):
        raise SelectionPolicyError("portfolio ids must be non-empty")
    known = set(ids)
    for name, ranking in (
        ("secondary_ranking", request.secondary_ranking),
        ("specialist_ranking", request.specialist_ranking),
    ):
        if len(ranking) != len(set(ranking)):
            raise SelectionPolicyError(f"{name} ids must be unique")
        unknown = tuple(candidate_id for candidate_id in ranking if candidate_id not in known)
        if unknown:
            raise SelectionPolicyError(f"{name} contains unknown candidates: {', '.join(unknown)}")


def _bounded(request: SelectionRequest, limit: int) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
    ids = tuple(item.candidate_id for item in request.candidates)
    return ids[:limit], f"top{limit}", (f"rank-prefix:{limit}",)


def _portfolio(
    request: SelectionRequest, *, limit: int, relevance_passes: int
) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
    """Select across declared portfolios, then fill by original rank.

    ``relevance_passes`` controls how many leading candidates keep strict rank priority
    before portfolio coverage. It is a deterministic search-space policy, not a quality
    estimate.
    """

    candidates = request.candidates
    selected = list(candidates[: min(relevance_passes, limit)])
    selected_ids = {item.candidate_id for item in selected}
    represented = {item.portfolio for item in selected}
    for item in candidates:
        if len(selected) == limit:
            break
        if item.candidate_id not in selected_ids and item.portfolio not in represented:
            selected.append(item)
            selected_ids.add(item.candidate_id)
            represented.add(item.portfolio)
    for item in candidates:
        if len(selected) == limit:
            break
        if item.candidate_id not in selected_ids:
            selected.append(item)
            selected_ids.add(item.candidate_id)
    return (
        tuple(item.candidate_id for item in selected),
        f"portfolio-{limit}",
        (f"rank-prefix:{relevance_passes}", "portfolio-coverage", "stable-rank-fill"),
    )


def _progressive(
    request: SelectionRequest,
) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
    ids = tuple(item.candidate_id for item in request.candidates)
    stage = ProgressiveStage(request.progressive_stage)
    limits = {
        ProgressiveStage.TOP3: 3,
        ProgressiveStage.TOP5: 5,
        ProgressiveStage.CATALOG: len(ids),
    }
    limit = limits[stage]
    return ids[:limit], stage.value, ("caller-declared-expansion-stage",)


def _dual(request: SelectionRequest) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
    if not request.secondary_ranking:
        raise SelectionPolicyError("dual-agent/v1 requires secondary_ranking")
    primary = tuple(item.candidate_id for item in request.candidates)
    merged: list[str] = []
    for index in range(max(len(primary), len(request.secondary_ranking))):
        for ranking in (primary, request.secondary_ranking):
            if index < len(ranking) and ranking[index] not in merged:
                merged.append(ranking[index])
            if len(merged) == 5:
                return tuple(merged), "dual-merge", ("round-robin-rank-merge", "deduplicate")
    return tuple(merged), "dual-merge", ("round-robin-rank-merge", "deduplicate")


def _conditional_specialist(
    request: SelectionRequest,
) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
    primary = tuple(item.candidate_id for item in request.candidates)
    if not request.activate_specialist:
        return primary[:5], "generalist", ("specialist-not-activated", "rank-prefix:5")
    if not request.specialist_ranking:
        raise SelectionPolicyError(
            "conditional-specialist/v1 requires specialist_ranking when activated"
        )
    merged = tuple(dict.fromkeys((*request.specialist_ranking, *primary)))[:5]
    return merged, "specialist", ("specialist-activated", "specialist-first", "stable-rank-fill")


def _full(request: SelectionRequest) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
    return (
        tuple(item.candidate_id for item in request.candidates),
        "full-catalog",
        ("control-no-shortlist",),
    )


_Policy = Callable[[SelectionRequest], tuple[tuple[str, ...], str, tuple[str, ...]]]
_POLICIES: dict[SelectionStrategy, _Policy] = {
    SelectionStrategy.TOP5: lambda request: _bounded(request, 5),
    SelectionStrategy.PORTFOLIO_BALANCED_5: lambda request: _portfolio(
        request, limit=5, relevance_passes=2
    ),
    SelectionStrategy.PORTFOLIO_EXPLORATORY_8: lambda request: _portfolio(
        request, limit=8, relevance_passes=1
    ),
    SelectionStrategy.PROGRESSIVE_3_5_CATALOG: _progressive,
    SelectionStrategy.DUAL_AGENT: _dual,
    SelectionStrategy.CONDITIONAL_SPECIALIST: _conditional_specialist,
    SelectionStrategy.FULL_CATALOG_CONTROL: _full,
}


def select(request: SelectionRequest) -> SelectionResult:
    """Execute one registered policy and return a complete deterministic trace."""

    _validate(request)
    strategy = SelectionStrategy.parse(request.strategy)
    try:
        selected, stage, codes = _POLICIES[strategy](request)
    except KeyError as exc:  # Defensive if an enum is added without an implementation.
        raise SelectionPolicyError(f"selection strategy is not implemented: {strategy.value}") from exc
    considered = tuple(item.candidate_id for item in request.candidates)
    trace = SelectionTrace(
        contract_version=CONTRACT_VERSION,
        requested_strategy=strategy,
        executed_strategy=strategy,
        stage=stage,
        considered_ids=considered,
        selected_ids=selected,
        decision_codes=codes,
    )
    return SelectionResult(selected_ids=selected, trace=trace)


__all__ = [
    "CONTRACT_VERSION",
    "ProgressiveStage",
    "RUNTIME_SHADOW_ONLY_STRATEGIES",
    "SelectionCandidate",
    "SelectionExecution",
    "SelectionPolicyError",
    "SelectionRequest",
    "SelectionResult",
    "SelectionStrategy",
    "SelectionTrace",
    "live_cache_fragment",
    "runtime_execution",
    "select",
]
