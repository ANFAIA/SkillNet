"""The mastery rule, case by case (§7.2, §7.3, §7.5). No DB, no network.

What is asserted here is what a certificate ends up claiming, so the interesting tests
are the adversarial ones: getting two items right by chance must not master a critical
node, failing "apply" must never master anything, every threshold must be reachable,
and a competent-but-imperfect learner must actually be able to finish the course.
"""

from dataclasses import dataclass
from datetime import datetime

import pytest

from src.services.mastery_service import (
    ALPHA,
    APPLY_FLOOR,
    DOUBT_BAND_FLOOR,
    FADING_STREAK,
    HINT_LIMIT,
    MASTERY_PRIOR,
    REGRESS_STREAK,
    SIGNAL_REINFORCE,
    THRESHOLDS,
    W3_APPLY,
    W3_CONSTRUCTED,
    W3_UNDERSTAND,
    WORKED_SOLUTION_FAILURES,
    W_APPLY,
    W_UNDERSTAND,
    evaluate_course_completion,
    ewma,
    mastery_prior,
    may_offer_hint,
    next_mastery,
    probe_estimate,
    probe_item_count,
    probe_verdict,
    requires_tiebreak,
    scaffold_band_for,
    shu_ha_ri,
    skill_level_for,
    target_bloom,
    threshold_for,
    tiebreak_mastery,
    tiebreak_verdict,
    transition_close_probe,
    transition_on_answer,
    transition_open_node,
)

CRITICALITIES = ("critical", "recommended", "contextual")
# Five levels per item -> the 25-case truth table of §12.2. The four deterministic
# graders only ever return 0.0 or 1.0, but the rule must stay sane on the
# intermediate values an LLM-graded open item can produce.
SCORE_LEVELS = (0.0, 0.25, 0.5, 0.75, 1.0)


# --- constants ---------------------------------------------------------------


def test_constants_match_the_spec():
    assert THRESHOLDS == {"critical": 0.90, "recommended": 0.80, "contextual": 0.70}
    assert (W_APPLY, W_UNDERSTAND) == (0.6, 0.4)
    assert (W3_APPLY, W3_UNDERSTAND, W3_CONSTRUCTED) == (0.45, 0.15, 0.40)
    assert DOUBT_BAND_FLOOR == 0.55
    assert (FADING_STREAK, REGRESS_STREAK) == (3, 2)
    assert ALPHA == 0.4
    assert HINT_LIMIT == 3
    assert WORKED_SOLUTION_FAILURES == 4
    # The weights must add up, or the estimate is not on a 0..1 scale.
    assert W_APPLY + W_UNDERSTAND == pytest.approx(1.0)
    assert W3_APPLY + W3_UNDERSTAND + W3_CONSTRUCTED == pytest.approx(1.0)


def test_probe_item_count_and_tiebreak_by_criticality():
    assert probe_item_count("critical") == 3
    assert probe_item_count("recommended") == 2
    assert probe_item_count("contextual") == 2
    assert requires_tiebreak("critical") is True
    assert requires_tiebreak("recommended") is False


def test_threshold_for_prefers_the_per_node_column():
    assert threshold_for("critical") == 0.90
    assert threshold_for("contextual") == 0.70
    assert threshold_for("critical", 0.75) == 0.75


# --- §7.2 the probe verdict --------------------------------------------------


@pytest.mark.parametrize("score_a", SCORE_LEVELS)
@pytest.mark.parametrize("score_b", SCORE_LEVELS)
def test_probe_verdict_truth_table(score_a, score_b):
    """25 cases per criticality, checked against the rule stated in prose."""
    for criticality in CRITICALITIES:
        verdict, est = probe_verdict(score_a, score_b, criticality)
        assert est == pytest.approx(0.6 * score_a + 0.4 * score_b)

        if score_a < APPLY_FLOOR:
            expected = "learning"
        elif est >= 1.0:
            expected = "tiebreak" if criticality == "critical" else "mastered"
        elif est >= DOUBT_BAND_FLOOR:
            expected = "tiebreak"
        else:
            expected = "learning"
        assert verdict == expected, (criticality, score_a, score_b)


def test_perfect_b_with_a_at_zero_is_never_mastery():
    """Rule 1 of §7.2: you cannot master a node while failing the "apply" item."""
    for criticality in CRITICALITIES:
        verdict, est = probe_verdict(0.0, 1.0, criticality)
        assert verdict == "learning"
        assert est == pytest.approx(0.4)


def test_two_lucky_items_do_not_master_a_critical_node():
    """The false positive this whole rule exists to stop.

    Two 4-option items are guessed right 1 time in 16. On a critical node that must
    not be enough, and combined with the single scored probe per schema version
    (§3.4) the brute-force strategy disappears.
    """
    verdict, est = probe_verdict(1.0, 1.0, "critical")
    assert verdict == "tiebreak"
    assert est == pytest.approx(1.0)
    # ...and the tie-break is the only door to `mastered`.
    assert tiebreak_verdict(1.0, 1.0, 0.0, "critical")[0] == "learning"
    assert tiebreak_verdict(1.0, 1.0, 1.0, "critical")[0] == "mastered"


def test_two_perfect_items_master_a_non_critical_node():
    assert probe_verdict(1.0, 1.0, "recommended") == ("mastered", pytest.approx(1.0))
    assert probe_verdict(1.0, 1.0, "contextual") == ("mastered", pytest.approx(1.0))


def test_doubt_band_is_exactly_the_a_right_b_wrong_case():
    verdict, est = probe_verdict(1.0, 0.0, "recommended")
    assert (verdict, est) == ("tiebreak", pytest.approx(0.6))
    assert probe_estimate(1.0, 0.0) == pytest.approx(0.6)


# The §7.2 arithmetic table, verbatim.
TIEBREAK_TABLE = [
    (1.0, 1.0, 1.0, 1.00, "mastered", "mastered", "mastered"),
    (1.0, 0.0, 1.0, 0.85, "learning", "mastered", "mastered"),
    (1.0, 1.0, 0.0, 0.60, "learning", "learning", "learning"),
    (1.0, 0.0, 0.0, 0.45, "learning", "learning", "learning"),
]


@pytest.mark.parametrize(
    ("a", "b", "c", "expected_m", "critical", "recommended", "contextual"),
    TIEBREAK_TABLE,
)
def test_tiebreak_table_of_the_spec(a, b, c, expected_m, critical, recommended, contextual):
    assert tiebreak_mastery(a, b, c) == pytest.approx(expected_m)
    assert tiebreak_verdict(a, b, c, "critical")[0] == critical
    assert tiebreak_verdict(a, b, c, "recommended")[0] == recommended
    assert tiebreak_verdict(a, b, c, "contextual")[0] == contextual


def test_every_threshold_is_reachable_by_the_tiebreak():
    """The bug the renormalization fixed: the old tie-break topped out at 0.80, so
    0.90 was unreachable and the extra LLM call on a critical node was dead code."""
    assert tiebreak_mastery(1.0, 1.0, 1.0) == pytest.approx(1.0)
    for criticality, threshold in THRESHOLDS.items():
        assert tiebreak_mastery(1.0, 1.0, 1.0) >= threshold
        assert tiebreak_verdict(1.0, 1.0, 1.0, criticality)[0] == "mastered"


def test_thresholds_actually_discriminate():
    """0.85 separates critical from the other two; 0.60 masters none. If the three
    thresholds behaved alike, criticality would be decoration."""
    verdicts = {c: tiebreak_verdict(1.0, 0.0, 1.0, c)[0] for c in CRITICALITIES}
    assert verdicts == {
        "critical": "learning",
        "recommended": "mastered",
        "contextual": "mastered",
    }


def test_explicit_threshold_overrides_criticality():
    assert tiebreak_verdict(1.0, 0.0, 1.0, "critical", 0.80)[0] == "mastered"
    assert tiebreak_verdict(1.0, 1.0, 1.0, "contextual", 1.01)[0] == "learning"


# --- §7.1 prior and scaffold band -------------------------------------------


def test_mastery_prior_from_user_skills():
    assert MASTERY_PRIOR == {"high": 0.85, "medium": 0.55, "low": 0.25}
    assert mastery_prior("high") == 0.85
    assert mastery_prior("medium") == 0.55
    assert mastery_prior("low") == 0.25
    assert mastery_prior(None) == 0.0
    assert mastery_prior("unrecognized") == 0.0


def test_cold_start_first_node_with_no_profile_data():
    """The very first node of a brand-new user: no onboarding, no user_skills, nothing.

    Prior 0.0, neutral scaffolding (never novice — that is what `unknown` buys us),
    and the probe still decides in two items.
    """
    prior = mastery_prior(None)
    assert prior == 0.0

    opening = transition_open_node(prior=prior)
    assert opening.rule == 1
    assert opening.to_state == "probing"
    assert opening.changes == {"mastery": 0.0}
    assert opening.stamp_first_seen_at is True

    # `unknown` maps to neutral scaffolding, not novice.
    assert scaffold_band_for(experience_level=None, verdict="mastered") == "neutral"
    assert scaffold_band_for(experience_level="unknown", verdict="mastered") == "neutral"

    # And a clean probe still masters a non-critical node from a 0.0 prior.
    verdict, est = probe_verdict(1.0, 1.0, "recommended")
    closing = transition_close_probe(verdict=verdict, score=est, prior=prior)
    assert closing.to_state == "mastered"
    assert closing.changes["mastery"] == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("experience", "verdict", "score_a", "expected"),
    [
        ("none", "mastered", 1.0, "novice"),
        ("none", "tiebreak", 1.0, "novice"),  # the novice rule is evaluated first
        ("unknown", "learning", 0.0, "novice"),  # failed apply outright
        ("some", "learning", 0.5, "neutral"),
        ("unknown", "tiebreak", 1.0, "advanced"),
        ("experienced", "learning", 1.0, "advanced"),
        ("unknown", "mastered", 1.0, "neutral"),
    ],
)
def test_scaffold_band(experience, verdict, score_a, expected):
    band = scaffold_band_for(experience_level=experience, verdict=verdict, score_a=score_a)
    assert band == expected


# --- §3.3 derived views ------------------------------------------------------


def test_shu_ha_ri_and_target_bloom():
    assert shu_ha_ri(0.0, 0.80) == "shu"
    assert shu_ha_ri(0.49, 0.80) == "shu"
    assert shu_ha_ri(0.5, 0.80) == "ha"
    assert shu_ha_ri(0.79, 0.80) == "ha"
    assert shu_ha_ri(0.80, 0.80) == "ri"
    assert target_bloom(0.1, 0.80) == "understand"
    assert target_bloom(0.6, 0.80) == "apply"
    assert target_bloom(0.95, 0.80) == "analyze"


def test_skill_level_translation():
    assert skill_level_for(0.0) == "low"
    assert skill_level_for(0.49) == "low"
    assert skill_level_for(0.5) == "medium"
    assert skill_level_for(0.84) == "medium"
    assert skill_level_for(0.85) == "high"
    assert skill_level_for(1.0) == "high"


# --- §7.3 EWMA and the ceiling ----------------------------------------------


def test_ewma_arithmetic():
    assert ewma(0.0, 1.0) == pytest.approx(0.4)
    assert ewma(0.4, 1.0) == pytest.approx(0.64)
    assert ewma(0.64, 1.0) == pytest.approx(0.784)
    assert ewma(0.784, 1.0) == pytest.approx(0.8704)


def test_a_failure_never_raises_mastery():
    value = next_mastery(
        mastery_old=0.2, score=0.9, passed=False, consecutive_correct=0, threshold=0.80
    )
    assert value == pytest.approx(0.2)
    lower = next_mastery(
        mastery_old=0.8, score=0.0, passed=False, consecutive_correct=0, threshold=0.80
    )
    assert lower == pytest.approx(0.48)


def test_mastery_ceiling_lets_a_sustained_085_finish_a_critical_node():
    """The arithmetic bug the ceiling fixes.

    `0.6*old + 0.4*score` has its fixed point at `score`, so a learner who reliably
    scores 0.85 asymptotes at 0.85 and never reaches the 0.90 of a critical node.
    Since completion requires every critical node mastered, the course was
    permanently unfinishable with no way out.
    """
    threshold = THRESHOLDS["critical"]

    # Without the ceiling: the fixed point is 0.85, forever below 0.90.
    plain = 0.0
    for _ in range(50):
        plain = ewma(plain, 0.85)
    assert plain < threshold
    assert plain == pytest.approx(0.85, abs=1e-6)

    # With it: three consecutive correct answers ARE the sufficient evidence.
    mastery, streak = 0.0, 0
    for _ in range(3):
        streak += 1
        mastery = next_mastery(
            mastery_old=mastery,
            score=0.85,
            passed=True,
            consecutive_correct=streak,
            threshold=threshold,
        )
    assert streak == FADING_STREAK
    assert mastery >= threshold


def test_ceiling_does_not_fire_before_the_streak():
    mastery = next_mastery(
        mastery_old=0.0, score=0.85, passed=True, consecutive_correct=2, threshold=0.90
    )
    assert mastery == pytest.approx(0.34)


def test_mastery_stays_in_range():
    assert next_mastery(
        mastery_old=1.0, score=1.0, passed=True, consecutive_correct=5, threshold=1.0
    ) == pytest.approx(1.0)
    assert next_mastery(
        mastery_old=0.0, score=0.0, passed=False, consecutive_correct=0, threshold=0.8
    ) == pytest.approx(0.0)


# --- the 8 transitions of §7.3 ----------------------------------------------


def test_transition_1_not_started_to_probing():
    t = transition_open_node(prior=mastery_prior("medium"))
    assert (t.rule, t.to_state) == (1, "probing")
    assert t.changes == {"mastery": 0.55}
    assert t.stamp_first_seen_at is True
    assert t.increment_nodes_completed is False


def test_transition_2_probing_to_mastered_by_probe():
    verdict, est = probe_verdict(1.0, 1.0, "recommended")
    t = transition_close_probe(verdict=verdict, score=est, prior=0.25, scaffold_band="neutral")
    assert (t.rule, t.to_state) == (2, "mastered")
    assert t.changes["probe_score"] == pytest.approx(1.0)
    assert t.changes["mastery"] == pytest.approx(1.0)  # max(prior, estimate)
    assert t.changes["scaffold_band"] == "neutral"
    assert t.stamp_mastered_at is True
    # A node skipped by the probe must NOT count towards nodes_completed (§3.3).
    assert t.increment_nodes_completed is False


def test_transition_2_keeps_a_higher_prior():
    t = transition_close_probe(verdict="mastered", score=0.6, prior=0.85)
    assert t.changes["mastery"] == pytest.approx(0.85)
    assert t.changes["probe_score"] == pytest.approx(0.6)


def test_transition_3_probing_stays_probing_on_doubt():
    verdict, est = probe_verdict(1.0, 0.0, "recommended")
    assert verdict == "tiebreak"
    t = transition_close_probe(verdict=verdict, score=est, prior=0.25)
    assert (t.rule, t.to_state) == (3, "probing")
    assert t.serve_tiebreak is True
    assert t.changes == {}  # probe_score not written yet
    assert t.stamp_mastered_at is False


def test_transition_4_probing_to_mastered_by_tiebreak():
    verdict, m = tiebreak_verdict(1.0, 0.0, 1.0, "recommended")
    t = transition_close_probe(
        verdict=verdict, score=m, prior=0.0, from_tiebreak=True, scaffold_band="advanced"
    )
    assert (t.rule, t.to_state) == (4, "mastered")
    assert t.changes["probe_score"] == pytest.approx(0.85)
    assert t.changes["mastery"] == pytest.approx(0.85)
    assert t.stamp_mastered_at is True
    assert t.increment_nodes_completed is False


@pytest.mark.parametrize("from_tiebreak", [False, True])
def test_transition_5_probing_to_learning_keeps_the_prior(from_tiebreak):
    t = transition_close_probe(
        verdict="learning",
        score=0.4,
        prior=0.55,
        from_tiebreak=from_tiebreak,
        scaffold_band="neutral",
    )
    assert (t.rule, t.to_state) == (5, "learning")
    assert t.changes["probe_score"] == pytest.approx(0.4)
    # mastery is NOT touched: probe_score and mastery never overwrite each other.
    assert "mastery" not in t.changes
    assert t.changes["scaffold_band"] == "neutral"


def test_transition_6_learning_to_mastered_needs_threshold_and_streak():
    t = transition_on_answer(
        state="learning",
        mastery=0.784,
        consecutive_correct=2,
        consecutive_failed=0,
        score=1.0,
        passed=True,
        threshold=0.80,
    )
    assert (t.rule, t.to_state) == (6, "mastered")
    assert t.changes["consecutive_correct"] == 3
    assert t.changes["mastery"] >= 0.80
    assert t.increment_nodes_completed is True  # the ONLY place it is incremented
    assert t.stamp_mastered_at is True
    assert t.attempts_delta == 1


def test_transition_6_does_not_fire_without_the_streak():
    """A lucky spike is not mastery: a streak of 3 demands repeated generation."""
    t = transition_on_answer(
        state="learning",
        mastery=0.95,
        consecutive_correct=0,
        consecutive_failed=1,
        score=1.0,
        passed=True,
        threshold=0.80,
    )
    assert t.rule == 0
    assert t.to_state == "learning"
    assert t.changes["mastery"] >= 0.80
    assert t.increment_nodes_completed is False


def test_transition_7_two_failures_lower_the_difficulty_without_changing_state():
    t = transition_on_answer(
        state="learning",
        mastery=0.5,
        consecutive_correct=1,
        consecutive_failed=1,
        score=0.0,
        passed=False,
        threshold=0.80,
        error_kind="conceptual",
    )
    assert (t.rule, t.to_state) == (7, "learning")
    assert t.changes["consecutive_failed"] == REGRESS_STREAK
    assert t.changes["consecutive_correct"] == 0
    # A failure never *raises* mastery; it may lower it (0.6*0.5 + 0.4*0.0 = 0.3).
    assert t.changes["mastery"] == pytest.approx(0.3)
    assert t.changes["last_error_kind"] == "conceptual"
    assert t.signals == (SIGNAL_REINFORCE,)
    assert t.lower_difficulty is True


def test_transition_8_fourth_failure_hands_over_the_solution():
    t = transition_on_answer(
        state="learning",
        mastery=0.3,
        consecutive_correct=0,
        consecutive_failed=3,
        score=0.0,
        passed=False,
        threshold=0.80,
        hints_used=HINT_LIMIT,
        item_failures=3,
    )
    # `learning`, not `mastered`: seeing the answer after four failures demonstrates
    # nothing, and it is a state the learner can carry on from.
    assert (t.rule, t.to_state) == (8, "learning")
    assert t.show_worked_solution is True
    assert t.attempts_delta == 1


def test_transition_8_fires_without_a_single_hint_asked():
    """**The reason the rule changed.** Four failures, zero hints, and the exit opens.

    Rule 8 used to require ``hints_used >= HINT_LIMIT`` as well, which made the escape
    hatch conditional on the learner *asking* for it. A learner who never asks failed the
    same item for ever — and the Didact closers, which are the default check of a node,
    have no hint ladder to ask on at all. The failures alone are the evidence now.
    """
    t = transition_on_answer(
        state="learning",
        mastery=0.3,
        consecutive_correct=0,
        consecutive_failed=3,
        score=0.0,
        passed=False,
        threshold=0.80,
        hints_used=0,
        item_failures=WORKED_SOLUTION_FAILURES - 1,
    )
    assert (t.rule, t.to_state) == (8, "learning")
    assert t.show_worked_solution is True


def test_transition_8_still_needs_the_fourth_failure():
    """The negative branch asserts ``show_worked_solution``, **not** the state.

    Every branch of ``transition_on_answer`` returns ``learning`` for a failure, so
    asserting ``to_state == "learning"`` here would pass whether or not rule 8 fired and
    would test nothing. The flag is what separates them, and three failures do not earn it
    however many hints were spent: the exit is a *count of failures*, not a purchase.
    """
    too_early = transition_on_answer(
        state="learning",
        mastery=0.3,
        consecutive_correct=0,
        consecutive_failed=1,
        score=0.0,
        passed=False,
        threshold=0.80,
        hints_used=HINT_LIMIT,
        item_failures=2,
    )
    assert too_early.rule != 8
    assert too_early.show_worked_solution is False

    passing = transition_on_answer(
        state="learning",
        mastery=0.3,
        consecutive_correct=0,
        consecutive_failed=3,
        score=1.0,
        passed=True,
        threshold=0.80,
        hints_used=0,
        item_failures=WORKED_SOLUTION_FAILURES,
    )
    assert passing.rule != 8
    assert passing.show_worked_solution is False


def test_the_eight_transitions_are_all_covered():
    """One assertion that the numbering is complete and unique: all 8 rows of the §7.3
    table are still reachable, rule 8 included."""
    seen = {
        transition_open_node(prior=0.0).rule,
        transition_close_probe(verdict="mastered", score=1.0, prior=0.0).rule,
        transition_close_probe(verdict="tiebreak", score=0.6, prior=0.0).rule,
        transition_close_probe(
            verdict="mastered", score=0.85, prior=0.0, from_tiebreak=True
        ).rule,
        transition_close_probe(verdict="learning", score=0.4, prior=0.0).rule,
        transition_on_answer(
            state="learning",
            mastery=0.784,
            consecutive_correct=2,
            consecutive_failed=0,
            score=1.0,
            passed=True,
            threshold=0.80,
        ).rule,
        transition_on_answer(
            state="learning",
            mastery=0.5,
            consecutive_correct=0,
            consecutive_failed=1,
            score=0.0,
            passed=False,
            threshold=0.80,
        ).rule,
        transition_on_answer(
            state="learning",
            mastery=0.3,
            consecutive_correct=0,
            consecutive_failed=3,
            score=0.0,
            passed=False,
            threshold=0.80,
            hints_used=HINT_LIMIT,
            item_failures=3,
        ).rule,
    }
    assert seen == {1, 2, 3, 4, 5, 6, 7, 8}


# --- §7.4 hints and the escape hatch -----------------------------------------


def test_attempt_before_hint():
    assert may_offer_hint(item_attempts=0, hints_used=0) is False
    assert may_offer_hint(item_attempts=1, hints_used=0) is True
    assert may_offer_hint(item_attempts=1, hints_used=2) is True
    assert may_offer_hint(item_attempts=1, hints_used=HINT_LIMIT) is False


def test_the_hint_ladder_always_ends_in_an_escape():
    """The reason the ``needs_review`` state could be removed: the exit is the flag.

    A fourth failure of the same item, from the state the learner is actually in (here with
    the hints spent too, which no longer changes the verdict but is the common path).
    What has to hold is that the item stops being asked (``show_worked_solution``)
    and that the state left behind is one the learner can carry on from — ``learning``, whose
    every rule is still available to them, and never ``mastered``, which would stamp
    ``mastered_at`` and print an unearned number on a certificate.
    """
    t = transition_on_answer(
        state="learning",
        mastery=0.25,
        consecutive_correct=0,
        consecutive_failed=3,
        score=0.0,
        passed=False,
        threshold=0.90,
        hints_used=HINT_LIMIT,
        item_failures=HINT_LIMIT,
    )
    assert t.show_worked_solution is True
    assert t.to_state == "learning"
    assert t.stamp_mastered_at is False
    # The attempt is counted, and the mastery it earned (none) is still written.
    assert t.attempts_delta == 1
    assert t.changes["mastery"] <= 0.25

    # And from there the learner is not stuck: the ordinary rules still apply to the
    # next item, up to and including mastering the node.
    recovered = transition_on_answer(
        state=t.to_state,
        mastery=0.85,
        consecutive_correct=2,
        consecutive_failed=0,
        score=1.0,
        passed=True,
        threshold=0.90,
    )
    assert (recovered.rule, recovered.to_state) == (6, "mastered")


# --- §7.5 course closing -----------------------------------------------------


@dataclass
class FakeNodeProgress:
    node_id: str
    criticality: str
    state: str
    mastery: float
    archived: bool = False
    #: Migration 0029. `node_is_done` counts a node as done when it is mastered OR
    #: finished, so every fake needs the second column to answer for itself.
    completed_at: datetime | None = None


def test_course_completes_only_when_every_node_is_mastered():
    nodes = [
        FakeNodeProgress("n1", "critical", "mastered", 0.95),
        FakeNodeProgress("n2", "critical", "learning", 0.40),
        FakeNodeProgress("n3", "recommended", "not_started", 0.0),
        FakeNodeProgress("n4", "contextual", "learning", 0.0),
    ]
    result = evaluate_course_completion(nodes)
    assert result.can_complete is False
    # Every non-mastered node blocks now, regardless of criticality.
    assert result.blocked_by == ("n2", "n3", "n4")
    assert result.total_critical == 4
    assert result.mastered_critical == 1
    assert result.progress_percent == 25
    # Score is the mean over all nodes.
    assert result.score == pytest.approx((0.95 + 0.40 + 0.0 + 0.0) / 4)


def test_recommended_and_contextual_now_block():
    nodes = [
        FakeNodeProgress("n1", "critical", "mastered", 0.90),
        FakeNodeProgress("n2", "recommended", "learning", 0.10),
        FakeNodeProgress("n3", "contextual", "not_started", 0.0),
    ]
    result = evaluate_course_completion(nodes)
    assert result.can_complete is False
    assert result.blocked_by == ("n2", "n3")
    assert result.score == pytest.approx((0.90 + 0.10 + 0.0) / 3)


def test_archiving_the_missing_node_unblocks_the_course():
    """The §7.5 recalculation: archiving the node that was missing must complete the
    course, and adding a critical node must un-complete it."""
    blocking = FakeNodeProgress("n2", "critical", "learning", 0.30)
    nodes = [FakeNodeProgress("n1", "critical", "mastered", 0.90), blocking]
    assert evaluate_course_completion(nodes).can_complete is False

    blocking.archived = True
    reopened = evaluate_course_completion(nodes)
    assert reopened.can_complete is True
    assert reopened.total_critical == 1
    assert reopened.score == pytest.approx(0.90)

    nodes.append(FakeNodeProgress("n3", "critical", "not_started", 0.0))
    assert evaluate_course_completion(nodes).can_complete is False


def test_a_course_of_only_recommended_nodes_completes_when_mastered():
    # Criticality no longer gates closure: a mastered node completes regardless.
    nodes = [FakeNodeProgress("n1", "recommended", "mastered", 1.0)]
    result = evaluate_course_completion(nodes)
    assert result.can_complete is True
    assert result.score == pytest.approx(1.0)
    assert result.total_critical == 1


def test_an_empty_course_cannot_complete():
    result = evaluate_course_completion([])
    assert result.can_complete is False
    assert result.score is None
    assert result.total_critical == 0


def test_a_waived_node_counts_as_mastered():
    """§7.4's human escape hatch: `waive` sets `mastered`, so closing sees no
    difference — which is the point, and why it is audited."""
    nodes = [FakeNodeProgress("n1", "critical", "mastered", 0.0)]
    result = evaluate_course_completion(nodes)
    assert result.can_complete is True
    assert result.score == pytest.approx(0.0)
