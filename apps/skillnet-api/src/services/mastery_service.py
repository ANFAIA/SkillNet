"""The mastery rule (§7): computable, deterministic and not gameable.

Everything in this module is **pure**. No DB session, no LLM, no clock except the
one you pass in. That is deliberate: the rule that decides whether a safety-critical
node counts as mastered — and therefore what a certificate says — has to be
readable, testable case by case, and impossible to bend by re-entering a screen.

Three groups of functions:

1. **The probe verdict** (§7.2). ``probe_verdict`` over the two selected-response
   items, ``tiebreak_verdict`` over the constructed third one. The weights are
   renormalized so a perfect third item reaches 1.00 and *every* threshold is
   reachable; in the previous version the tie-break topped out at 0.80 and was dead
   code in a ``critical`` node.
2. **Mastery during the node** (§7.3). ``next_mastery`` is the EWMA *with the
   ceiling*: without it a sustained 0.85 asymptotes at 0.85 and never reaches the
   0.90 of a ``critical`` node, so the course could never be completed.
3. **The 8 transitions** of ``node_state``. Each returns a :class:`Transition`
   describing exactly which ``learner_node_states`` columns change; applying it to
   a row is the repository's job (``LearnerNodeStateRepository.apply_transition``),
   never this module's.

Course closing (§7.5) also lives here as ``evaluate_course_completion`` so the rule
is unit-testable without an enrollment; ``EnrollmentService`` (B11) calls it.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Protocol

# --- §7.2 the probe rule -----------------------------------------------------

THRESHOLDS: dict[str, float] = {"critical": 0.90, "recommended": 0.80, "contextual": 0.70}
DOUBT_BAND_FLOOR = 0.55
W_APPLY, W_UNDERSTAND = 0.6, 0.4
# Renormalized tie-break: a perfect third item reaches 1.0, so EVERY threshold is
# reachable and none is dead code.
W3_APPLY, W3_UNDERSTAND, W3_CONSTRUCTED = 0.45, 0.15, 0.40
# Failing the "apply" item can never yield mastery, whatever the other items say.
APPLY_FLOOR = 0.5

# --- §7.3 mastery during the node -------------------------------------------

ALPHA = 0.4  # weight of the new evidence in the EWMA
FADING_STREAK = 3  # N consecutive correct -> mastery ceiling + eligible for `mastered`
REGRESS_STREAK = 2  # consecutive failures -> lower difficulty + `reforzar_con_ejemplo`

# --- §7.4 scaffolding escalation --------------------------------------------

HINT_LIMIT = 3  # hints per item; the 4th failure after them exits to needs_review
NEEDS_REVIEW_FAILURES = 4

# --- §3.4 anti-retry ---------------------------------------------------------

REPROBE_COOLDOWN_DAYS = 7

# --- §7.1 prior from user_skills --------------------------------------------

MASTERY_PRIOR: dict[str, float] = {"high": 0.85, "medium": 0.55, "low": 0.25}

# --- §3.3 derived views (never persisted twice) ------------------------------

SKILL_LEVEL_MEDIUM_FLOOR = 0.5
SKILL_LEVEL_HIGH_FLOOR = 0.85
TARGET_BLOOM: dict[str, str] = {"shu": "understand", "ha": "apply", "ri": "analyze"}

ProbeVerdict = Literal["mastered", "tiebreak", "learning"]
Phase = Literal["shu", "ha", "ri"]
RenderHint = Literal["prefetch", "skip"]

# State values, spelled out so this module never imports the ORM.
NOT_STARTED = "not_started"
PROBING = "probing"
LEARNING = "learning"
MASTERED = "mastered"
NEEDS_REVIEW = "needs_review"

CRITICAL = "critical"

# The one signal §7.3 row 7 emits. The vocabulary itself is owned by B3
# (``LearnerProfileService.apply_signals``); this module only names it.
SIGNAL_REINFORCE = "reforzar_con_ejemplo"


def _value(raw: object) -> str:
    """Enum member or raw string -> its string value (same trick as ``resolve_delivery``)."""
    return raw.value if isinstance(raw, enum.Enum) else str(raw)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def threshold_for(criticality: object, node_threshold: float | None = None) -> float:
    """Effective mastery threshold. ``course_nodes.mastery_threshold`` wins when set.

    The threshold depends on the *criticality*, never on the person (§7.2 rule 4).
    """
    if node_threshold is not None:
        return _clamp(node_threshold)
    return THRESHOLDS[_value(criticality)]


def probe_item_count(criticality: object) -> int:
    """2 items, 3 on a ``critical`` node (§7.1)."""
    return 3 if _value(criticality) == CRITICAL else 2


def requires_tiebreak(criticality: object) -> bool:
    """On a ``critical`` node the constructed tie-break is mandatory, always (§7.2 rule 3)."""
    return _value(criticality) == CRITICAL


def probe_estimate(score_a: float, score_b: float) -> float:
    return W_APPLY * score_a + W_UNDERSTAND * score_b


def probe_verdict(
    score_a: float,
    score_b: float,
    criticality: object,
    threshold: float | None = None,
) -> tuple[ProbeVerdict, float]:
    """Verdict from ONLY the two selected-response items.

    ``threshold`` is accepted for symmetry with ``tiebreak_verdict`` and is
    deliberately unused: over two binary items the estimate can only take the four
    values {0.0, 0.4, 0.6, 1.0}, so pretending a continuous threshold discriminates
    there would be a lie. The per-criticality threshold does its real work in
    ``tiebreak_verdict`` and in the ``learning -> mastered`` transition of §7.3.
    """
    est = probe_estimate(score_a, score_b)
    if score_a < APPLY_FLOOR:  # failing "apply" -> never mastery
        return "learning", est
    if est >= 1.0:
        # Everything right. On a critical node that is NOT enough: chance is 1/16.
        if _value(criticality) == CRITICAL:
            return "tiebreak", est
        return "mastered", est
    if est >= DOUBT_BAND_FLOOR:  # 0.6 -> doubt band
        return "tiebreak", est
    return "learning", est


def tiebreak_mastery(score_a: float, score_b: float, score_c: float) -> float:
    return W3_APPLY * score_a + W3_UNDERSTAND * score_b + W3_CONSTRUCTED * score_c


def tiebreak_verdict(
    score_a: float,
    score_b: float,
    score_c: float,
    criticality: object,
    threshold: float | None = None,
) -> tuple[ProbeVerdict, float]:
    m = tiebreak_mastery(score_a, score_b, score_c)
    thr = threshold if threshold is not None else THRESHOLDS[_value(criticality)]
    return ("mastered" if m >= thr else "learning"), m


def mastery_prior(user_skill_level: object | None) -> float:
    """Seed for ``learner_node_states.mastery`` from ``user_skills.level`` (§7.1).

    Only a starting point for the EWMA and for ``scaffold_band``: it never skips a
    node on its own — that is the probe's job.
    """
    if user_skill_level is None:
        return 0.0
    return MASTERY_PRIOR.get(_value(user_skill_level), 0.0)


def scaffold_band_for(
    *,
    experience_level: object | None,
    verdict: ProbeVerdict | None,
    score_a: float = 0.0,
) -> str:
    """``novice`` | ``neutral`` | ``advanced``, computed ONCE when the probe closes (§3.3).

    ``verdict`` is the verdict of the two selected-response items (the tie-break does
    not move the band). The novice rule is evaluated first, so a declared novice who
    lands in the doubt band still gets novice scaffolding.
    """
    experience = _value(experience_level) if experience_level is not None else "unknown"
    if experience == "none":
        return "novice"
    if verdict == "learning" and score_a == 0:
        return "novice"
    if verdict == "tiebreak" or experience == "experienced":
        return "advanced"
    return "neutral"


def shu_ha_ri(mastery: float, threshold: float) -> Phase:
    if mastery < 0.5:
        return "shu"
    if mastery < threshold:
        return "ha"
    return "ri"


def skill_level_for(mastery: float) -> Literal["low", "medium", "high"]:
    """``mastery`` -> ``user_skills.level`` (§3.3). Applied upwards only by the caller."""
    if mastery < SKILL_LEVEL_MEDIUM_FLOOR:
        return "low"
    if mastery < SKILL_LEVEL_HIGH_FLOOR:
        return "medium"
    return "high"


def target_bloom(mastery: float, threshold: float) -> str:
    return TARGET_BLOOM[shu_ha_ri(mastery, threshold)]


def ewma(mastery_old: float, score: float) -> float:
    return (1 - ALPHA) * mastery_old + ALPHA * score


def next_mastery(
    *,
    mastery_old: float,
    score: float,
    passed: bool,
    consecutive_correct: int,
    threshold: float,
) -> float:
    """EWMA **with the ceiling** (§7.3). ``consecutive_correct`` is the count *after*
    this answer.

    The ceiling fixes a real arithmetic bug: ``0.6*old + 0.4*score`` has its fixed
    point at ``score``, so a competent-but-imperfect learner (a sustained 0.85) stayed
    0.05 below a critical node's threshold forever — and since completion requires
    every critical node mastered, the course was permanently unfinishable. Three
    consecutive correct answers *are* the sufficient evidence: the same streak that
    was already required, applied to the magnitude and not only to the counter.

    A failure never raises mastery.
    """
    value = ewma(mastery_old, score)
    if passed:
        if consecutive_correct >= FADING_STREAK:
            value = max(value, threshold)
    else:
        value = min(value, mastery_old)
    return _clamp(value)


def may_offer_hint(*, item_attempts: int, hints_used: int) -> bool:
    """``attempt-before-hint`` plus the hard cap of 3 (§7.4).

    ``item_attempts`` is the number of attempts already recorded in ``node_attempts``
    for that ``item_id``. A click-to-explain inside an unanswered ``QuizItem`` counts
    as a hint and consumes quota (§8.5) — the caller bumps ``hints_used`` for it.
    """
    return item_attempts >= 1 and hints_used < HINT_LIMIT


def may_reprobe(
    *,
    state: object,
    completed_at: datetime | None,
    now: datetime | None = None,
) -> bool:
    """Re-probe only from ``needs_review`` and only after 7 days (§3.4)."""
    if _value(state) != NEEDS_REVIEW:
        return False
    if completed_at is None:
        return False
    moment = now or datetime.now(timezone.utc)
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    return moment - completed_at >= timedelta(days=REPROBE_COOLDOWN_DAYS)


# --- the 8 transitions of §7.3 ----------------------------------------------


@dataclass(frozen=True)
class Transition:
    """One row of the §7.3 table, as data.

    ``rule`` is the row number (1..8); ``rule == 0`` is a graded answer that matches
    none of the numbered rows (plain EWMA update, still ``learning``).

    ``changes`` holds *absolute* values for ``learner_node_states`` columns other
    than ``state``; the boolean flags are the side effects the repository performs
    (timestamps it must stamp with its own clock, counters it must increment).
    """

    rule: int
    to_state: str
    changes: dict[str, Any] = field(default_factory=dict)
    signals: tuple[str, ...] = ()
    attempts_delta: int = 0
    increment_nodes_completed: bool = False
    stamp_first_seen_at: bool = False
    stamp_mastered_at: bool = False
    serve_tiebreak: bool = False
    lower_difficulty: bool = False
    show_worked_solution: bool = False


def transition_open_node(*, prior: float = 0.0) -> Transition:
    """1. ``not_started`` -> ``probing`` when the probe is requested.

    ``mastery`` is seeded with the prior from ``user_skills`` (§7.1).
    """
    return Transition(
        rule=1,
        to_state=PROBING,
        changes={"mastery": _clamp(prior)},
        stamp_first_seen_at=True,
    )


def transition_close_probe(
    *,
    verdict: ProbeVerdict,
    score: float,
    prior: float = 0.0,
    from_tiebreak: bool = False,
    scaffold_band: str | None = None,
) -> Transition:
    """2, 3, 4 and 5. What closing (or not closing) a probe does to the state.

    Two ambiguities that reach a certificate, closed here: ``mastery`` after a probe
    is written only when the verdict masters (``max(prior, estimate)``); a
    ``learning`` verdict keeps the prior, so ``probe_score`` and ``mastery`` never
    overwrite each other. And ``nodes_completed`` is NOT incremented by a probe —
    only by rule 6 — because a node skipped by the probe produced no interaction
    event and counting it would drop the learner out of calibration with an empty
    ``format_vector`` (§3.3).
    """
    if verdict == "tiebreak":
        # 3. Stays in `probing`; item C is served; probe_score not written yet.
        return Transition(rule=3, to_state=PROBING, serve_tiebreak=True)

    changes: dict[str, Any] = {"probe_score": _clamp(score)}
    if scaffold_band is not None:
        changes["scaffold_band"] = scaffold_band

    if verdict == "mastered":
        changes["mastery"] = _clamp(max(prior, score))
        return Transition(
            rule=4 if from_tiebreak else 2,
            to_state=MASTERED,
            changes=changes,
            stamp_mastered_at=True,
        )

    # 5. `learning`: probe_score written, mastery NOT touched (the prior stands).
    return Transition(rule=5, to_state=LEARNING, changes=changes)


def transition_on_answer(
    *,
    state: object,
    mastery: float,
    consecutive_correct: int,
    consecutive_failed: int,
    score: float,
    passed: bool,
    threshold: float,
    hints_used: int = 0,
    item_failures: int = 0,
    error_kind: object | None = None,
) -> Transition:
    """6, 7 and 8. What one graded answer inside the node does to the state.

    ``item_failures`` is how many failures the same ``item_id`` already has *before*
    this answer, so rule 8 fires on the 4th failure of that item once the 3 hints
    have been spent (§7.4). ``error_kind`` is written to ``last_error_kind`` only on
    a failure; it feeds the next ``genera_ui``.

    Requiring ``mastery >= threshold`` *and* a streak of 3 is what defends against
    cognitive offloading: a streak demands repeated generation, not a lucky spike.
    """
    if passed:
        streak_correct = consecutive_correct + 1
        streak_failed = 0
    else:
        streak_correct = 0
        streak_failed = consecutive_failed + 1

    new_mastery = next_mastery(
        mastery_old=mastery,
        score=score,
        passed=passed,
        consecutive_correct=streak_correct,
        threshold=threshold,
    )
    changes: dict[str, Any] = {
        "mastery": new_mastery,
        "consecutive_correct": streak_correct,
        "consecutive_failed": streak_failed,
    }
    if not passed and error_kind is not None:
        changes["last_error_kind"] = _value(error_kind)

    if (
        not passed
        and item_failures + 1 >= NEEDS_REVIEW_FAILURES
        and hints_used >= HINT_LIMIT
    ):
        # 8. The only producer of `needs_review` in this PR. Worked solution shown,
        # the node joins the practice queue and stays visible and re-enterable.
        return Transition(
            rule=8,
            to_state=NEEDS_REVIEW,
            changes=changes,
            attempts_delta=1,
            show_worked_solution=True,
        )

    if passed and new_mastery >= threshold and streak_correct >= FADING_STREAK:
        # 6. The ONLY place `nodes_completed` is incremented.
        return Transition(
            rule=6,
            to_state=MASTERED,
            changes=changes,
            attempts_delta=1,
            increment_nodes_completed=True,
            stamp_mastered_at=True,
        )

    if not passed and streak_failed >= REGRESS_STREAK:
        # 7. Lower the difficulty; the state does not change.
        return Transition(
            rule=7,
            to_state=LEARNING,
            changes=changes,
            signals=(SIGNAL_REINFORCE,),
            attempts_delta=1,
            lower_difficulty=True,
        )

    current = _value(state)
    return Transition(
        rule=0,
        to_state=LEARNING if current in (NOT_STARTED, PROBING, LEARNING) else current,
        changes=changes,
        attempts_delta=1,
    )


# --- §7.5 course closing -----------------------------------------------------


class NodeProgressLike(Protocol):
    """Just enough of ``(course_nodes, learner_node_states)`` to close a course.

    Structurally typed on purpose: tests pass plain dataclasses and nothing here
    imports the ORM.
    """

    node_id: Any
    criticality: Any
    archived: bool
    state: Any
    mastery: float


@dataclass(frozen=True)
class CourseCompletion:
    """The computable form of ``enrollments.status`` / ``score`` (§7.5)."""

    can_complete: bool
    blocked_by: tuple[str, ...]
    score: float | None
    mastered_critical: int
    total_critical: int
    progress_percent: int


def evaluate_course_completion(
    nodes: Iterable[NodeProgressLike],
) -> CourseCompletion:
    """Completion depends ONLY on non-archived ``critical`` nodes being ``mastered``.

    ``recommended`` and ``contextual`` never block. ``score`` is the mean ``mastery``
    over exactly those critical nodes — the number a certificate prints, which is why
    it may not depend on implementation details. A course with no critical node at
    all cannot complete (the validation gate of §11.1 requires at least one, so this
    only happens mid-edit).

    Called by ``EnrollmentService`` (B11), including the mandatory recalculation for
    every active enrollment when ``PUT /courses/{id}/schema`` changes the critical set.
    """
    critical = [n for n in nodes if _value(n.criticality) == CRITICAL and not n.archived]
    total = len(critical)
    if total == 0:
        return CourseCompletion(
            can_complete=False,
            blocked_by=(),
            score=None,
            mastered_critical=0,
            total_critical=0,
            progress_percent=0,
        )

    blocked = tuple(str(n.node_id) for n in critical if _value(n.state) != MASTERED)
    mastered = total - len(blocked)
    score = sum(_clamp(n.mastery) for n in critical) / total
    return CourseCompletion(
        can_complete=not blocked,
        blocked_by=blocked,
        score=score,
        mastered_critical=mastered,
        total_critical=total,
        progress_percent=round(100 * mastered / total),
    )
