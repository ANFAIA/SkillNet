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

from src.services.node_progression import course_progression, is_done


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
