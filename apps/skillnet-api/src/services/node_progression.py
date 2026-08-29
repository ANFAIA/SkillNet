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

**Progression is linear, and that is a decision.** Every course is a sequence you walk
through. Mastery is still measured, still stored, still shown — a certificate means exactly
what it meant — but it does not govern navigation: ``available`` is always ``True``.
Prerequisites survive in the schema, where they order the tree and feed the tutor's
``revisar_prerrequisito`` signal; what they no longer do is close doors.

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


def _enum_value(raw: object) -> str:
    """Enum member or raw string -> its string value, as ``resolve_delivery`` does."""
    return str(getattr(raw, "value", raw))


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
    #: May the learner open it? Always ``True`` while progression is linear. It is a
    #: *answer*, not a permission: the field survives the arrival of a mode that steers,
    #: and the name says what the client should do with it.
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

    __slots__ = ("archived", "completed_at", "criticality", "mastery", "node_id", "state")

    def __init__(
        self,
        *,
        node_id: uuid.UUID,
        criticality: Any,
        archived: bool,
        state: str,
        mastery: float,
        completed_at: Any,
    ) -> None:
        self.node_id = node_id
        self.criticality = criticality
        self.archived = archived
        self.state = state
        self.mastery = mastery
        self.completed_at = completed_at


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


def course_progression(
    nodes: Sequence[Any],
    states: Mapping[uuid.UUID, Any],
) -> CourseProgression:
    """Snapshot of one learner in one course.

    ``nodes`` are the course's non-archived nodes in position order; ``states`` maps node
    id to that learner's ``learner_node_states`` row, absent for a node never touched.
    """
    rows = [
        _Row(
            node_id=node.id,
            criticality=node.criticality,
            archived=bool(getattr(node, "archived", False)),
            state=_enum_value(getattr(states.get(node.id), "state", NOT_STARTED)),
            mastery=float(getattr(states.get(node.id), "mastery", 0.0) or 0.0),
            completed_at=getattr(states.get(node.id), "completed_at", None),
        )
        for node in nodes
    ]
    done_by_id = {row.node_id: node_is_done(row) for row in rows}

    progressions = tuple(
        NodeProgression(
            node_id=node.id,
            position=int(node.position),
            state=row.state,
            mastery=row.mastery,
            done=done_by_id[node.id],
            # Linear: nothing is ever closed. See the module docstring.
            available=True,
            first_seen_at=getattr(states.get(node.id), "first_seen_at", None),
            completed_at=row.completed_at,
        )
        for node, row in zip(nodes, rows, strict=True)
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
    "CourseProgression",
    "NodeProgression",
    "course_progression",
    "is_done",
]
