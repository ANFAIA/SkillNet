"""The mastery rule (§7): computable, deterministic and not gameable.

Everything in this module is **pure**. No DB session, no LLM, no clock at all.
That is deliberate: the rule that decides whether a safety-critical
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

HINT_LIMIT = 3  # hints per item: a DISCLOSURE BUDGET, not a precondition for the exit
# How many failures of the SAME item buy the worked solution. Named after what it produces
# and not after a state: it used to be `NEEDS_REVIEW_FAILURES`, and the state it named
# outlived its own removal in this comment for exactly that reason.
#
# The two constants are deliberately independent. `HINT_LIMIT` caps how much a learner may
# be told; `WORKED_SOLUTION_FAILURES` is evidence that the item is not working for them.
# Gating the second on the first said "you get rescued only once you have spent your rescue
# budget", which is circular, and it punished exactly the learners who never ask.
WORKED_SOLUTION_FAILURES = 4

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

    ``item_failures`` is how many failures **the one item being answered** already has
    *before* this answer, so rule 8 fires on the 4th failure of that item (§7.4). "Item"
    means whatever the caller's path uses to identify a single question: ``item_id`` on
    ``POST /nodes/{id}/answer``, ``binding_id`` on ``POST /activities/{id}/attempts``, and
    ``activity_id`` on ``POST /activities/{id}/evaluate``. It is
    **not** a node-wide counter, and the difference is not cosmetic — a node-wide count lets
    failures on one activity open the answer to the next one, and every one after it, which
    empties the node's evidence of meaning while looking like it works. A caller that cannot
    count per item must say so where it calls, not quietly pass the nearest number.

    ``error_kind`` is written to ``last_error_kind`` only on a failure; it feeds the
    next ``genera_ui``.

    ``hints_used`` is still taken, still recorded as evidence and still caps disclosure
    through :func:`may_offer_hint` — but it no longer *governs* rule 8. See that rule.

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

    if not passed and item_failures + 1 >= WORKED_SOLUTION_FAILURES:
        # 8. **The emergency exit**, and the only thing that closes an item the learner
        # is not going to get right. Four failures of the same item: the worked solution
        # is handed over and the learner carries on.
        #
        # The rule used to demand `hints_used >= HINT_LIMIT` as well, and that made the
        # exit depend on the learner *asking* for help. Three consequences, all bad and
        # all measured on the Didact closers, which have no hint ladder at all: a learner
        # who never asks fails the same item for ever; the learners least likely to ask
        # are the ones most in need of the exit; and the condition was circular — a
        # disclosure budget (`HINT_LIMIT`) was being used as the price of a rescue. Four
        # failures are evidence the item is not working, whatever was or was not asked
        # for, so the failures alone are the condition now.
        #
        # This branch must never be deleted "because the state it produced is gone". The
        # state was only a label; without the branch the answer falls through to rule 0,
        # `show_worked_solution` stays `False`, and the learner re-attempts the same item
        # for ever with no way out — which is the failure mode §7.4 exists to prevent.
        #
        # `LEARNING` and not `MASTERED`: failing four times and being shown the answer
        # demonstrates nothing, and `mastered` stamps `mastered_at` and feeds a
        # certificate. The learner stays where they were, one item lighter.
        return Transition(
            rule=8,
            to_state=LEARNING,
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
    #: ``learner_node_states.completed_at`` (migration 0029), or ``None``. Half of what
    #: :func:`node_is_done` reads — see the reasoning there.
    completed_at: Any


@dataclass(frozen=True)
class CourseCompletion:
    """The computable form of ``enrollments.status`` (§7.5).

    It used to carry ``enrollments.score`` too. It no longer does: finishing a course
    says that it was finished, and nothing else. See :func:`evaluate_course_completion`
    for why that number was removed rather than improved.
    """

    can_complete: bool
    blocked_by: tuple[str, ...]
    #: Nodes this learner is **done** with (:func:`node_is_done`), out of ``total_critical``.
    #: The two names are §7.5's and predate both the drop of the criticality gate and
    #: ``completed_at``; they are kept because they are the API contract of
    #: ``NodeListRead``. Read them as "done nodes" and "nodes".
    mastered_critical: int
    total_critical: int
    progress_percent: int


def node_is_done(node: NodeProgressLike) -> bool:
    """Has this learner finished this node? Mastered **or** worked through to the end.

    The one definition of "done", read by both halves of :func:`evaluate_course_completion`
    — ``progress_percent`` and ``can_complete``. That they share it is the point: see the
    note in that function.

    ``mastered`` alone was the rule and it was unsatisfiable for a large part of the
    product. Rule 6 of §7.3 requires ``consecutive_correct >= FADING_STREAK`` on graded
    items, and an expository node — a worked example, a checklist, a summary — has no
    graded item to answer. Such a node stays ``not_started`` for ever, contributes 0 to
    progress, and blocks closure permanently. ``completed_at`` (migration 0029) is the
    recorded fact that the learner reached the end of it.

    The two are not merged and neither is derived from the other: ``mastered`` is
    evidence of a demonstration, ``completed_at`` is evidence of work done. Both close
    a node; neither is a grade, and since 2026-08-29 neither is graded afterwards: a
    finished course accredits its skills for having been finished, so nothing downstream
    needs to tell the two apart.
    """
    return _value(node.state) == MASTERED or node.completed_at is not None


def evaluate_course_completion(
    nodes: Iterable[NodeProgressLike],
) -> CourseCompletion:
    """Completion depends on EVERY non-archived node being **done** (:func:`node_is_done`).

    Criticality does not gate closure: the learner must get through the whole course.
    A course with no node at all cannot complete (only happens mid-edit on an empty
    schema).

    **A finished course says that it was finished. It carries no grade, and it derives
    none.** This function used to also return ``score``, the mean ``mastery`` over *every*
    non-archived node, and ``apply_dynamic_closure`` wrote it to ``enrollments.score`` as
    the mark of the course. That mean could not tell two zeros apart: an expository node
    has no graded item, so it contributes 0 meaning *nobody asked*, while a node failed
    outright contributes 0 meaning *they got it wrong*. Averaged together and printed as a
    mark, a learner who read a well-made expository course end to end was recorded at 0.0,
    the same figure as one who answered everything wrong.

    Dropping the mark left a second copy of the same mistake for a day: a
    ``measured_mastery`` average over the nodes that *had* asked something, fed to
    ``mastery_to_level`` so a completion accredited the course's skills at
    ``low``/``medium``/``high``. That is gone too, and for the owner's reason rather than a
    technical one — **there are no exams here**. Two criteria for one event (the
    certificate says "completed", the skill said "at level X") is one criterion too many,
    and the weaker of the two was derived from whatever fraction of the course happened to
    carry graded items. Finishing a course now accredits the skills that course covers, at
    one level, full stop; see ``EnrollmentService.close_dynamic_if_mastered`` for where
    that grant happens and for the per-node accreditation that should eventually replace
    it.

    **Progress and closure use the same predicate, and that is a decision.** They are two
    outputs of the one ``blocked`` set below, so ``progress_percent == 100`` and
    ``can_complete`` cannot disagree. Making closure stricter — "reading counts towards
    the bar, but a ``critical`` node still has to be mastered to close the course" — was
    considered and rejected for two reasons. First, it would put two definitions of
    "done" in a module whose whole reason for existing is that this rule is written once.
    Second, the stricter branch is not a higher standard but an unreachable one: mastery
    needs a streak of three correct graded answers and an expository ``critical`` node
    has nothing to answer, so a course containing one would show 100% and never close —
    the exact "the bar is full and nothing happened" the split was meant to prevent. The
    honest place for the distinction was never closure, and it is not a mark or a derived
    skill level either: it is ``SkillService.record_mastery``, per node, where the number
    comes from evidence about the one skill it accredits.

    Called by ``EnrollmentService`` (B11), including the mandatory recalculation for
    every active enrollment when ``PUT /courses/{id}/schema`` changes the node set.
    """
    critical = [n for n in nodes if not n.archived]
    total = len(critical)
    if total == 0:
        return CourseCompletion(
            can_complete=False,
            blocked_by=(),
            mastered_critical=0,
            total_critical=0,
            progress_percent=0,
        )

    blocked = tuple(str(n.node_id) for n in critical if not node_is_done(n))
    mastered = total - len(blocked)
    return CourseCompletion(
        can_complete=not blocked,
        blocked_by=blocked,
        mastered_critical=mastered,
        total_critical=total,
        progress_percent=round(100 * mastered / total),
    )
