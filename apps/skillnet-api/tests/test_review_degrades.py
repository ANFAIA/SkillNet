"""A reviewer that cannot run must not throw away the course it was going to review.

`review_quality` is the fifth of five LLM calls in the v1 pipeline. Themes, structure
and modules already exist by the time it runs, and it produces none of them — it judges
them. Letting a provider failure there reach `node_error_wrapper` routed the graph to
`handle_error` and discarded all four earlier calls.

Measured on 2026-07-27 generating "Introduccion neurociencia" against Groq's free tier:
6000 tokens per minute, and a review call that asks for most of a minute's worth in one
request. The job died at `review_quality` twice in a row with `RateLimitError` while the
modules sat finished in the graph state.

The course now ships unreviewed — as a **draft**, which an admin still has to publish,
so the human gate the reviewer feeds into is untouched. What must never happen is that
it ships unreviewed *quietly*.
"""

from __future__ import annotations

import pytest

from src.agents.content.routing import MAX_REFINEMENT_CYCLES, route_after_quality_review


def _state(report, **extra):
    return {"review_report": report, **extra}


def test_a_skipped_review_publishes_instead_of_failing():
    report = {"passed": False, "review_skipped": True, "overall_score": 0.0, "issues": []}
    assert route_after_quality_review(_state(report)) == "pass"


def test_a_skipped_review_does_not_try_to_refine():
    """Refinement consumes the reviewer's issue list. With no reviewer there is no list,
    so refining would be a second call producing nothing from nothing — and on the very
    provider that just refused."""
    report = {
        "passed": False,
        "review_skipped": True,
        "issues": [{"severity": "critical", "module_index": 0, "detail": "x"}],
    }
    assert route_after_quality_review(_state(report, refinement_count=0)) == "pass"


def test_no_report_at_all_is_still_a_failure():
    """The degraded path is opt-in and explicit. A missing report means the node did not
    reach its own error handling, which is a real fault and must not be laundered into a
    published course."""
    assert route_after_quality_review({}) == "fail"
    assert route_after_quality_review({"review_report": None}) == "fail"


# --- everything the reviewer decides when it *does* run is unchanged ------------------
def test_a_passing_review_still_passes():
    assert route_after_quality_review(_state({"passed": True})) == "pass"


def test_critical_issues_still_refine():
    report = {"passed": False, "issues": [{"severity": "critical"}]}
    assert route_after_quality_review(_state(report, refinement_count=0)) == "refine"


def test_only_minor_issues_still_pass():
    report = {"passed": False, "issues": [{"severity": "minor"}, {"severity": "minor"}]}
    assert route_after_quality_review(_state(report, refinement_count=0)) == "pass"


def test_the_refinement_budget_still_ends_the_loop():
    report = {"passed": False, "issues": [{"severity": "critical"}]}
    routed = route_after_quality_review(
        _state(report, refinement_count=MAX_REFINEMENT_CYCLES)
    )
    assert routed == "pass"


@pytest.mark.parametrize("flag", [False, None, 0, ""])
def test_a_falsy_skip_flag_is_not_a_skip(flag):
    """`review_skipped` is set only by the node's own except branch. Anything falsy is
    an ordinary report and must be judged on its issues."""
    report = {"passed": False, "review_skipped": flag, "issues": [{"severity": "critical"}]}
    assert route_after_quality_review(_state(report, refinement_count=0)) == "refine"
