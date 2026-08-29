"""Per-(user, activity) server-owned counters for Didact activities.

**Why this table exists at all.** ``mastery_service.transition_on_answer`` contracts
``item_failures`` as "failures of the *one* question being answered". Every path that
grades has a place to count that — ``POST /nodes/{id}/answer`` counts rows of
``node_attempts`` keyed by ``item_id``, ``POST /activities/{id}/attempts`` counts
``experience_attempts`` keyed by ``binding_id`` — except the one that grades the default
closer of a node: ``POST /activities/{id}/evaluate``. Activities reached there are
materialized at runtime **without** an ``ImplementationBinding``, so nothing durable was
keyed by ``activity_id`` and the route passed ``learner_node_states.consecutive_failed``
instead, with the deviation written out in a comment. Node-wide is not per-activity: three
failures on one activity plus one on the next handed the second one's answer over.

**Why neither existing attempt table could hold it.**

* ``experience_attempts`` requires ``intent_id``, ``variant_id`` and ``binding_id``, all
  ``NOT NULL``. The activities that need counting are exactly the ones with no binding, so
  the rows could not be written without making three foreign keys optional and voiding the
  invariant that every provider-neutral evidence row traces back to a planned intent.
* ``node_attempts`` requires ``item_type``, an ``exercise_type`` enum of the six v1 item
  shapes. ``didact.matching``, ``didact.hotspot`` and ``didact.numeric-question`` are none
  of them, so a row could only be written by dropping the ``NOT NULL`` or by widening a
  v1 enum that ``exercises`` and ``exercise_attempts`` also live on. Dropping the
  constraint is not an additive migration — its ``downgrade`` cannot restore ``NOT NULL``
  over rows this feature wrote — and widening the enum is irreversible in PostgreSQL.

``activity_states`` is the right *key* and the wrong *owner*: its ``state`` column is an
opaque draft the learner writes through ``PUT /activities/{id}/state``. A counter that
decides when an answer is disclosed cannot share a row with a blob the client controls.

**Counters, not a log.** The sibling this mirrors is ``learner_node_states``, one level
down: a small row of server-owned numbers per learner and per unit of work. The three
things the routes need — has this learner tried at all, how many times have they missed,
how much has already been disclosed — are counts, and there is no reader that needs the
individual submissions. The graded verdicts that *are* worth keeping already go to
``learning_events`` as ``didact.graded``.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, UUIDMixin


class LearnerActivityState(UUIDMixin, TimestampMixin, Base):
    """What one learner has spent on one activity. Written only by the server."""

    __tablename__ = "learner_activity_states"
    __table_args__ = (
        CheckConstraint("attempts_count >= 0", name="ck_las_attempts"),
        CheckConstraint("failures_count >= 0", name="ck_las_failures"),
        CheckConstraint(
            "failures_count <= attempts_count", name="ck_las_failures_within_attempts"
        ),
        CheckConstraint("hints_used >= 0", name="ck_las_hints"),
        UniqueConstraint("activity_id", "user_id", name="uq_las_learner"),
        Index("idx_las_user", "user_id"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    activity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("activity_definitions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    #: Graded submissions of this activity, pass or fail. The ``attempt-before-hint`` gate
    #: of §7.4 reads this and nothing else: asking for help before trying is refused.
    attempts_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    #: How many of those missed. Lifetime, never reset by a pass — the same reading
    #: ``NodeAttemptRepository.count_failures_for_item`` gives the node ladder, so rule 8
    #: fires on the fourth failure of *this* activity whatever happened in between.
    failures_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    #: The disclosure budget already spent here, capped at ``HINT_LIMIT``. Only
    #: ``POST /activities/{id}/hint`` moves it; a number the client sends is ignored.
    hints_used: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0"), default=0
    )
    #: When the learner asked to be shown the answer and was shown it.
    #:
    #: **A record, not an accreditation.** Nothing about mastery is written alongside it,
    #: for the same reason ``POST /nodes/{id}/complete`` stamps ``completed_at`` without
    #: touching ``mastery``: asking for the answer demonstrates nothing, and a number
    #: invented here would end up on the same scale a certificate is read from.
    #:
    #: Never moved once set — the question it answers is "was this activity opened", and
    #: a second click is the same activity, still open.
    solution_revealed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
