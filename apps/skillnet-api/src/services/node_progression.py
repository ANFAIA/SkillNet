"""Where a learner stands in a course. One question, one place that answers it.

Everything here is **pure**: nodes in, learner states in, a snapshot out. No session, no
LLM, no clock. The repository does the reading; this decides what the reading means.

**Why this module exists at all.** A node carries two independent facts, and the system
only ever named one of them:

============  ==========================  ==================================
axis          question                    where it lives
============  ==========================  ==================================
evidence      has it been demonstrated?   ``state``, ``mastery``, ``mastered_at``
traversal     has it been worked through? ``first_seen_at``, ``completed_at``
============  ==========================  ==================================

§7 started with the evidence axis alone, so "done" meant ``mastered``. Migration 0029
found the hole — an expository node has no graded item, so it can never be demonstrated
however completely it was read — and added ``completed_at``. It added a *column*, not a
*concept*: nobody named the union, so every consumer spelled it out again and two of them
got it wrong. ``routes/nodes.py`` compared prerequisites against ``mastered`` and
``activity_progress`` did the same, both of them writing the predicate by hand outside the
module that owns it. That is not a coincidence — it is what happens to a rule that has no
single home.

The cost was not cosmetic. A learner would finish an expository node, ``completed_at``
would be stamped, progress would rise — and the next node stayed locked for ever, because
its prerequisite would never be ``mastered``. Reproduced against the API: a three-node
course pinned at 33 % with no action able to move it. And the failure mode is not only
editorial: a node that *should* carry an evaluation can end up without one when generation
falls back or drops a phantom component, which produces the identical dead end without
anybody having decided anything.

So the fix is not to correct the comparison in the route. It is to make sure there is only
one comparison, here, and to have the route ask instead of derive.

**Mastery does not govern navigation, and that is still the decision.** Mastery is
measured, stored and shown — a certificate means exactly what it meant — but it opens
nothing. Prerequisites survive in the schema, where they order the tree and feed the
tutor's ``revisar_prerrequisito`` signal; what they no longer do is close doors.

**What does govern it is ``courses.navigation_mode``**, chosen by whoever creates the
course (migration 0034). ``free`` is the default and is exactly the behaviour above: the
whole list is open. ``sequential`` opens a lesson when the one before it is *done*.

The distinction between *done* and *mastered* is the whole reason a lock can exist here
again without recreating the dead end this module was written to end. ``done`` is
reachable on every node — a learner can always finish one — whereas ``mastered`` is
unreachable on any node with no graded item, which is how the old padlocks pinned courses
at 33 % for ever. A rule built on ``done`` cannot produce a door nobody can open.

Two properties of the sequential rule are load-bearing rather than incidental:

* **A node the learner has already finished stays open.** Otherwise switching a
  half-walked course to ``sequential`` would shut lessons behind somebody who had already
  passed through them — retroactive punishment for a setting an admin changed.
* **Admins are exempt** (``resolve_navigation``), by role and never by enrollment, for
  the same reason ``services/course_access`` exempts them: previewing a course you are
  reviewing must not stop at lesson two.

**Where this forks later.** When the mastery mode arrives it will bring material of its own
— an observer that writes new screens mid-lesson — and that is a different kind of course,
not a flag on this one. The seam is the *producer* of :class:`CourseProgression`; the
contract callers depend on is the dataclass, never the shape of whatever builds it. That is
why this is a function today and not an interface with one implementation: the second one
will be asynchronous and carry dependencies this one has never needed, and guessing its
signature now would fix the wrong shape. See ``docs/design/future-progression-modes.md``.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from src.services.mastery_service import (
    CourseCompletion,
    evaluate_course_completion,
    node_is_done,
)

NOT_STARTED = "not_started"

#: The two values of ``courses.navigation_mode``. Spelled here as plain strings, not
#: imported from ``src.models``, so this module keeps taking values rather than rows and
#: stays testable with nothing but literals. ``CourseNavigationMode`` remains the source
#: of truth for what may be stored.
FREE = "free"
SEQUENTIAL = "sequential"


def _enum_value(raw: object) -> str:
    """Enum member or raw string -> its string value, as ``resolve_delivery`` does."""
    return str(getattr(raw, "value", raw))


def navigation_mode(course: Any) -> str:
    """The order rule this course *declares*, read defensively.

    ``getattr`` with a fallback for the same reason the projectors in
    ``routes/courses.py`` use one: a course row that predates migration 0034 — and every
    hand-built ``Course`` stand-in in the unit tests — must read ``free``, the behaviour
    everything had before the column existed, rather than crash a listing.
    """
    raw = getattr(course, "navigation_mode", None)
    if raw is None:
        return FREE
    value = _enum_value(raw)
    return value if value in (FREE, SEQUENTIAL) else FREE


def resolve_navigation(course: Any, *, is_admin: bool = False) -> str:
    """The order rule that applies to *this* request. One decision point, like
    ``course_delivery.resolve_delivery``.

    Same shape as that function on purpose: a declared column, a gate that says whether
    it is honoured, and a fall-back that is the permissive value. Here the gate is the
    caller's role — an admin walking a course they are reviewing is not a learner being
    paced, and stopping their preview at lesson two would make the setting unusable by
    the only person who can set it.

    Takes a bool rather than the user, so this module never learns what a user is; the
    routes already have ``course_access.is_admin`` as the one definition of that read.
    """
    if is_admin:
        return FREE
    return navigation_mode(course)


@dataclass(frozen=True, slots=True)
class NodeProgression:
    """One node, as this learner stands in front of it."""

    node_id: uuid.UUID
    position: int
    #: The evidence machine, untouched and reported as-is.
    state: str
    mastery: float
    #: The union of the two axes — ``mastered`` **or** worked through to the end. The one
    #: predicate, computed once. Nothing outside this module recomputes it.
    done: bool
    #: May the learner open it? Always ``True`` in ``free`` navigation; in ``sequential``,
    #: true for the first node, for one whose predecessor is ``done``, and for one this
    #: learner has already finished. It is an *answer*, not a permission: the field
    #: survives the arrival of a mode that steers, and the name says what the client
    #: should do with it.
    available: bool
    first_seen_at: Any = None
    completed_at: Any = None


@dataclass(frozen=True, slots=True)
class CourseProgression:
    """The whole snapshot a client needs to render a course for one learner.

    This is the stable contract. Whether a plain function, a strategy object or an agent
    produced it is invisible to every caller, which is exactly the property that lets the
    producer change later without touching a single call site.
    """

    nodes: tuple[NodeProgression, ...]
    #: Where to go now: the first node not yet done, in order. ``None`` when the course is
    #: finished (or empty). **The server answers this instead of shipping a list for the
    #: client to filter** — a steering observer cannot live in a browser, so the day the
    #: answer stops being "the next one" nothing on the client has to change.
    next_node_id: uuid.UUID | None
    completion: CourseCompletion

    @property
    def progress_percent(self) -> int:
        return self.completion.progress_percent

    @property
    def can_complete(self) -> bool:
        return self.completion.can_complete

    @property
    def blocked_by(self) -> tuple[str, ...]:
        return self.completion.blocked_by


class _Row:
    """``(node, learner state)`` in the shape ``mastery_service`` reads.

    Deliberately not the ORM row: the rule spans both tables and neither holds both
    halves. Structural, like ``NodeProgressLike``, so tests can pass anything.
    """

    __slots__ = (
        "archived",
        "attempts_count",
        "completed_at",
        "criticality",
        "mastery",
        "node_id",
        "probe_score",
        "state",
    )

    def __init__(
        self,
        *,
        node_id: uuid.UUID,
        criticality: Any,
        archived: bool,
        state: str,
        mastery: float,
        completed_at: Any,
        attempts_count: int = 0,
        probe_score: float | None = None,
    ) -> None:
        self.node_id = node_id
        self.criticality = criticality
        self.archived = archived
        self.state = state
        self.mastery = mastery
        self.completed_at = completed_at
        self.attempts_count = attempts_count
        self.probe_score = probe_score


def is_done(state_row: Any) -> bool:
    """Is this learner done with the node this row belongs to?

    The single entry point for the question, for callers that hold one learner state and
    no course around it (``activity_progress``). ``None`` — never opened — is not done.
    """
    if state_row is None:
        return False
    return node_is_done(
        _Row(
            node_id=getattr(state_row, "node_id", None),
            criticality=None,
            archived=False,
            state=_enum_value(getattr(state_row, "state", NOT_STARTED)),
            mastery=float(getattr(state_row, "mastery", 0.0) or 0.0),
            completed_at=getattr(state_row, "completed_at", None),
        )
    )


def _availability(done: Sequence[bool], navigation: str) -> tuple[bool, ...]:
    """``available`` for each node, in order. The one place the rule is written.

    In ``sequential`` a node opens when the one before it is done — plus two exits that
    are not softenings but corrections:

    * the **first** node has no predecessor, so it is always open (otherwise the course
      could never be started);
    * a node **already done** stays open, so switching a half-walked course to
      ``sequential`` never closes a lesson behind the learner who walked it. Without this
      a learner who had taken nodes out of order under ``free`` would find finished work
      locked, which is the retroactive punishment the mode is not for.

    Deliberately *not* keyed on ``first_seen_at``: having been shown a lesson is not the
    same as having got through it, and the anticipatory prefetch touches nodes ahead.
    """
    if navigation != SEQUENTIAL:
        return tuple(True for _ in done)
    return tuple(
        index == 0 or done[index - 1] or done[index] for index in range(len(done))
    )


def course_progression(
    nodes: Sequence[Any],
    states: Mapping[uuid.UUID, Any],
    *,
    navigation: str = FREE,
) -> CourseProgression:
    """Snapshot of one learner in one course.

    ``nodes`` are the course's non-archived nodes in position order; ``states`` maps node
    id to that learner's ``learner_node_states`` row, absent for a node never touched.

    ``navigation`` is the course's order rule as ``resolve_navigation`` resolved it for
    this request. It arrives as a **value and not as the course row** on purpose: the
    contract of this function is nodes-and-states in, snapshot out, and handing it a
    ``Course`` would give it a second source of truth to read from and a reason to grow
    opinions about rows. A string keeps it a pure mapping, keeps every test a literal,
    and — because it defaults to ``FREE`` — leaves every existing call site meaning
    exactly what it meant before the mode existed.
    """
    rows = [
        _Row(
            node_id=node.id,
            criticality=node.criticality,
            archived=bool(getattr(node, "archived", False)),
            state=_enum_value(getattr(states.get(node.id), "state", NOT_STARTED)),
            mastery=float(getattr(states.get(node.id), "mastery", 0.0) or 0.0),
            completed_at=getattr(states.get(node.id), "completed_at", None),
            # Read here too, not just in `EnrollmentService`: this snapshot carries a
            # whole `CourseCompletion`, and one built from rows that claim nothing was
            # ever measured would be a second, quieter answer to the same question.
            attempts_count=int(getattr(states.get(node.id), "attempts_count", 0) or 0),
            probe_score=getattr(states.get(node.id), "probe_score", None),
        )
        for node in nodes
    ]
    done = [node_is_done(row) for row in rows]
    available = _availability(done, navigation)

    progressions = tuple(
        NodeProgression(
            node_id=node.id,
            position=int(node.position),
            state=row.state,
            mastery=row.mastery,
            done=is_it_done,
            available=is_it_available,
            first_seen_at=getattr(states.get(node.id), "first_seen_at", None),
            completed_at=row.completed_at,
        )
        for node, row, is_it_done, is_it_available in zip(
            nodes, rows, done, available, strict=True
        )
    )

    next_node_id = next(
        (item.node_id for item in progressions if not item.done),
        None,
    )
    return CourseProgression(
        nodes=progressions,
        next_node_id=next_node_id,
        completion=evaluate_course_completion(rows),
    )


__all__ = [
    "FREE",
    "SEQUENTIAL",
    "CourseProgression",
    "NodeProgression",
    "course_progression",
    "is_done",
    "navigation_mode",
    "resolve_navigation",
]
