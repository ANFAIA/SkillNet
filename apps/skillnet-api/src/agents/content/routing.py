"""Conditional edge routing for the content generation graph."""

from __future__ import annotations

from src.agents.content.state import GenerationState

MAX_REFINEMENT_CYCLES = 2


def route_after_quality_review(state: GenerationState) -> str:
    """Decide what happens after the quality reviewer runs.

    Returns one of ``"pass"``, ``"refine"``, ``"fail"``.
    """
    report = state.get("review_report")

    if not report:
        return "fail"

    if report.get("passed"):
        return "pass"

    # Exhausted the refinement budget: hand off best effort rather than loop.
    if state.get("refinement_count", 0) >= MAX_REFINEMENT_CYCLES:
        return "pass"

    issues = report.get("issues") or []

    if any(issue.get("severity") == "critical" for issue in issues):
        return "refine"

    if issues and all(issue.get("severity") == "minor" for issue in issues):
        return "pass"

    # Major issues (or an empty non-passing report): try to refine.
    return "refine"
