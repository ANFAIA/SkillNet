"""Where a learner stands in a course — and the dead end this module exists to end.

The regression these tests carry is not hypothetical. It shipped, and it was reproduced
against the running API before the fix: a three-node course, chained by prerequisites,
where the learner finished the first node and the second stayed locked for ever because
that node could never become ``mastered``. Progress read 33 %, ``can_complete`` read
false, and no action existed that could move either.

Nothing covered it, which is why it survived. These are that cover.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from src.services.node_progression import (
    FREE,
    SEQUENTIAL,
    course_progression,
    is_done,
    navigation_mode,
    resolve_navigation,
)


def node(position: int, *, criticality: str = "recommended") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        position=position,
        criticality=criticality,
        archived=False,
        title=f"Nodo {position}",
        summary="…",
    )


def read(**kwargs) -> SimpleNamespace:
    """A ``learner_node_states`` row, with the columns this module reads."""
    return SimpleNamespace(
        state=kwargs.get("state", "not_started"),
        mastery=kwargs.get("mastery", 0.0),
        completed_at=kwargs.get("completed_at"),
        first_seen_at=kwargs.get("first_seen_at"),
    )


NOW = "2026-08-29T10:00:00Z"


# --------------------------------------------------------------------------------- #
# The dead end
# --------------------------------------------------------------------------------- #
def test_a_finished_expository_node_is_done_even_though_it_is_not_mastered() -> None:
    """The half of "done" that ``state`` cannot carry.

    An expository node — a summary, a worked example, a checklist — has no graded item to
    answer, so rule 6 of §7.3 can never fire and it stays ``not_started`` however
    completely it was read. ``completed_at`` is the record that the work happened.
    """
    first = node(1)
    progression = course_progression([first], {first.id: read(completed_at=NOW)})

    assert progression.nodes[0].state == "not_started"
    assert progression.nodes[0].done is True
    assert progression.progress_percent == 100
    assert progression.can_complete is True


def test_the_node_after_a_finished_expository_one_is_reachable() -> None:
    """**The regression.** This is the case that pinned real courses at 33 %.

    The route used to compare a prerequisite against ``mastered`` while every other
    consumer had moved to ``node_is_done``. A learner who finished node 1 found node 2
    closed, with nothing they could ever do to open it.
    """
    first, second, third = node(1), node(2), node(3)
    progression = course_progression(
        [first, second, third],
        {first.id: read(completed_at=NOW)},
    )

    assert [item.available for item in progression.nodes] == [True, True, True]
    assert progression.next_node_id == second.id
    assert progression.progress_percent == 33


def test_a_node_that_lost_its_evaluation_to_a_generation_failure_does_not_trap_anybody(
) -> None:
    """Same shape, different cause, and the reason this matters more than it looks.

    A node that *should* carry an evaluation can end up without one when the render falls
    back or drops a phantom component. Nobody decided that node would be expository — it
    broke. Under the old rule every such failure locked a learner out permanently, so the
    frequency of the dead end tracked the generation failure rate rather than anything an
    author wrote.
    """
    broken, following = node(1, criticality="critical"), node(2)
    progression = course_progression(
        [broken, following],
        {broken.id: read(completed_at=NOW, mastery=0.0)},
    )

    assert progression.nodes[0].done is True
    assert progression.nodes[1].available is True
    assert progression.next_node_id == following.id


# --------------------------------------------------------------------------------- #
# next_node_id — the server answering instead of shipping a list to filter
# --------------------------------------------------------------------------------- #
def test_next_node_is_the_first_one_not_done_in_order() -> None:
    first, second, third = node(1), node(2), node(3)
    progression = course_progression(
        [first, second, third],
        {first.id: read(state="mastered", mastery=0.95), third.id: read(completed_at=NOW)},
    )

    assert progression.next_node_id == second.id


def test_a_finished_course_has_no_next_node() -> None:
    first, second = node(1), node(2)
    progression = course_progression(
        [first, second],
        {first.id: read(state="mastered", mastery=0.9), second.id: read(completed_at=NOW)},
    )

    assert progression.next_node_id is None
    assert progression.can_complete is True
    assert progression.progress_percent == 100


def test_an_empty_course_has_no_next_node_and_cannot_complete() -> None:
    progression = course_progression([], {})

    assert progression.nodes == ()
    assert progression.next_node_id is None
    assert progression.can_complete is False


def test_a_learner_who_has_started_nothing_is_pointed_at_the_first_node() -> None:
    first, second = node(1), node(2)
    progression = course_progression([first, second], {})

    assert progression.next_node_id == first.id
    assert progression.progress_percent == 0
    assert progression.blocked_by == (str(first.id), str(second.id))


# --------------------------------------------------------------------------------- #
# Progression is linear: mastery is measured, it does not govern
# --------------------------------------------------------------------------------- #
def test_everything_is_available_however_little_has_been_demonstrated() -> None:
    """No padlocks. A course is a sequence you walk through.

    Mastery keeps being measured and reported — ``mastery`` and ``state`` are still on
    every row — but it decides nothing about where the learner may go.
    """
    nodes = [node(1, criticality="critical"), node(2), node(3)]
    progression = course_progression(nodes, {})

    assert all(item.available for item in progression.nodes)
    assert all(item.mastery == 0.0 for item in progression.nodes)


def test_mastery_and_state_are_reported_untouched() -> None:
    only = node(1)
    progression = course_progression(
        [only], {only.id: read(state="learning", mastery=0.62, first_seen_at=NOW)}
    )

    assert progression.nodes[0].state == "learning"
    assert progression.nodes[0].mastery == 0.62
    assert progression.nodes[0].first_seen_at == NOW
    assert progression.nodes[0].done is False


# --------------------------------------------------------------------------------- #
# is_done, for callers holding one row and no course
# --------------------------------------------------------------------------------- #
def test_is_done_reads_both_halves() -> None:
    assert is_done(None) is False
    assert is_done(read()) is False
    assert is_done(read(state="learning", mastery=0.8)) is False
    assert is_done(read(state="mastered", mastery=0.95)) is True
    assert is_done(read(completed_at=NOW)) is True


# --------------------------------------------------------------------------------- #
# navigation_mode — the dial that decides whether the sequence is enforced
# --------------------------------------------------------------------------------- #
def course(mode: str | None = None) -> SimpleNamespace:
    """A course row, with the one column ``navigation_mode`` reads."""
    return SimpleNamespace(navigation_mode=mode)


def test_free_is_what_a_course_without_the_column_reads() -> None:
    """Migration 0034 is additive and defaulted, and so is every reader of it.

    A row from before the column — and every hand-built stand-in in these suites — must
    read ``free``, the behaviour everything already had, rather than crash a listing or,
    worse, quietly pace a course nobody chose to pace.
    """
    assert navigation_mode(course(None)) == FREE
    assert navigation_mode(SimpleNamespace()) == FREE
    assert navigation_mode(course("sequential")) == SEQUENTIAL
    # A stale or garbage value degrades to the permissive one: locking people out is the
    # expensive direction to be wrong in.
    assert navigation_mode(course("mastery")) == FREE


def test_an_admin_walks_any_course_freely() -> None:
    """The preview must not stop at lesson two.

    By role and never by enrollment, for the reason ``services/course_access`` gives: the
    admin reviewing a course is exactly the person the library self-enrolled through
    "Probar curso", so an enrollment row cannot tell the reviewer from the learner.
    """
    assert resolve_navigation(course("sequential"), is_admin=True) == FREE
    assert resolve_navigation(course("sequential")) == SEQUENTIAL
    assert resolve_navigation(course("free"), is_admin=True) == FREE


def test_free_navigation_opens_everything_however_little_is_done() -> None:
    """The default, and the proof that adding the dial changed nobody's course."""
    nodes = [node(1, criticality="critical"), node(2), node(3)]

    default = course_progression(nodes, {})
    explicit = course_progression(nodes, {}, navigation=FREE)

    assert [item.available for item in default.nodes] == [True, True, True]
    assert [item.available for item in explicit.nodes] == [True, True, True]


def test_sequential_opens_only_the_first_lesson_to_begin_with() -> None:
    first, second, third = node(1), node(2), node(3)

    progression = course_progression([first, second, third], {}, navigation=SEQUENTIAL)

    assert [item.available for item in progression.nodes] == [True, False, False]
    assert progression.next_node_id == first.id


def test_sequential_a_finished_expository_node_opens_the_next_one() -> None:
    """**The regression of the old padlocks, in the mode that has locks again.**

    This is the case that must never come back. The node is expository, so it will never
    be ``mastered`` — ``state`` stays ``not_started`` however completely it was read — and
    under the rule that was removed its successor was shut for ever, with no action able
    to open it. The rule is written on ``done`` (``mastered`` **or** finished) and a
    learner can always finish a node. So the door opens.
    """
    first, second, third = node(1), node(2), node(3)

    progression = course_progression(
        [first, second, third],
        {first.id: read(completed_at=NOW)},
        navigation=SEQUENTIAL,
    )

    assert progression.nodes[0].state == "not_started"
    assert progression.nodes[0].done is True
    assert [item.available for item in progression.nodes] == [True, True, False]
    assert progression.next_node_id == second.id


def test_sequential_mastering_a_node_opens_the_next_one_too() -> None:
    """The other half of ``done``: demonstrated rather than merely finished."""
    first, second = node(1), node(2)

    progression = course_progression(
        [first, second],
        {first.id: read(state="mastered", mastery=0.95)},
        navigation=SEQUENTIAL,
    )

    assert [item.available for item in progression.nodes] == [True, True]


def test_sequential_a_node_that_lost_its_evaluation_still_opens_the_next_one() -> None:
    """The same guarantee when nobody *decided* the node would be expository.

    A render that falls back or drops a phantom component leaves a node with nothing
    graded to answer. Under a rule keyed on ``mastered`` the frequency of the dead end
    tracked the generation failure rate; keyed on ``done``, a broken node is finished like
    any other and the course keeps moving.
    """
    broken, following = node(1, criticality="critical"), node(2)

    progression = course_progression(
        [broken, following],
        {broken.id: read(completed_at=NOW, mastery=0.0)},
        navigation=SEQUENTIAL,
    )

    assert progression.nodes[1].available is True


def test_sequential_opening_a_lesson_is_not_finishing_it() -> None:
    """``first_seen_at`` must not unlock: the prefetch pins renders for nodes ahead.

    If having been *shown* a lesson counted, the anticipatory prefetch would walk the
    course on the learner's behalf and the mode would enforce nothing.
    """
    first, second = node(1), node(2)

    progression = course_progression(
        [first, second],
        {first.id: read(first_seen_at=NOW, state="learning", mastery=0.4)},
        navigation=SEQUENTIAL,
    )

    assert progression.nodes[0].done is False
    assert progression.nodes[1].available is False


def test_sequential_never_closes_a_lesson_behind_a_learner_already_past_it() -> None:
    """**Switching a half-walked course must not punish anybody retroactively.**

    A learner took nodes 1, 3 and 4 while the course was ``free`` — which was allowed, and
    is the whole point of ``free``. Turning the dial to ``sequential`` today must not shut
    3 and 4, work they have already done. It does not, because a node that is itself
    ``done`` stays open; what the mode paces is the road ahead.
    """
    nodes = [node(position) for position in range(1, 6)]
    walked = {
        nodes[0].id: read(completed_at=NOW),
        nodes[2].id: read(completed_at=NOW),
        nodes[3].id: read(completed_at=NOW),
    }

    progression = course_progression(nodes, walked, navigation=SEQUENTIAL)

    assert [item.available for item in progression.nodes] == [
        True,  # the first lesson, always
        True,  # its predecessor (1) is done
        True,  # already done itself — never taken away
        True,  # already done itself
        True,  # its predecessor (4) is done, so the frontier is open
    ]


def test_sequential_a_learner_mid_course_keeps_the_lesson_they_are_on() -> None:
    """The ordinary mid-course learner: three sealed, standing on the fourth."""
    nodes = [node(position) for position in range(1, 7)]
    walked = {nodes[index].id: read(completed_at=NOW) for index in range(3)}

    progression = course_progression(nodes, walked, navigation=SEQUENTIAL)

    assert [item.available for item in progression.nodes] == [
        True,
        True,
        True,
        True,
        False,
        False,
    ]
    assert progression.next_node_id == nodes[3].id


def test_sequential_changes_navigation_and_nothing_a_certificate_reads() -> None:
    """The dial steers where the learner may go and touches no measurement.

    ``progress_percent``, ``can_complete`` and ``blocked_by`` come from
    ``mastery_service``, which never hears about the mode — so a course cannot start
    reporting a different completion because somebody changed how it is walked.
    """
    nodes = [node(1), node(2), node(3)]
    walked = {nodes[0].id: read(completed_at=NOW)}

    free = course_progression(nodes, walked, navigation=FREE)
    sequential = course_progression(nodes, walked, navigation=SEQUENTIAL)

    assert free.progress_percent == sequential.progress_percent == 33
    assert free.can_complete is sequential.can_complete is False
    assert free.blocked_by == sequential.blocked_by
    assert free.next_node_id == sequential.next_node_id


def test_sequential_on_an_empty_course_says_nothing_and_does_not_crash() -> None:
    progression = course_progression([], {}, navigation=SEQUENTIAL)

    assert progression.nodes == ()
    assert progression.next_node_id is None
