"""learner_activity_states: what one learner has spent on one Didact activity

Revision ID: 0035
Revises: 0034
Create Date: 2026-08-29

Rule 8 of §7.3 hands the worked solution over on the fourth failure of **one question**,
and ``mastery_service.transition_on_answer`` says so in its contract: ``item_failures``
counts the item being answered, never the node. Two of the three grading paths could
honour that — ``POST /nodes/{id}/answer`` counts ``node_attempts`` by ``item_id``,
``POST /activities/{id}/attempts`` counts ``experience_attempts`` by ``binding_id``. The
third could not. ``POST /activities/{id}/evaluate`` grades the default closer of a node,
an activity materialized at runtime **without** an ``ImplementationBinding``, and nothing
durable was keyed by ``activity_id``, so the route passed
``learner_node_states.consecutive_failed`` — a node-wide streak — with the deviation
written out in a comment above the call. The cost was real and invisible: three failures
on one activity plus one on the next opened the second one's answer.

Two more things fall out of the same gap. The hint quota shown to a learner in front of a
Didact activity was ``node_attempts.hints_used``, which only ``POST /nodes/{id}/hint``
writes and which is scoped to a node's quiz item, so "te quedan N pistas" was counting
something else entirely. And a solution the learner asked to see lived only in the
browser's component state, so a reload reopened an activity that had been closed.

**Why a table and not a column somewhere.**

* ``experience_attempts`` has ``intent_id``, ``variant_id`` and ``binding_id`` ``NOT
  NULL``. The activities that need counting are exactly the unbound ones.
* ``node_attempts`` has ``item_type`` ``NOT NULL`` over the ``exercise_type`` enum — the
  six v1 item shapes, none of which describes ``didact.matching`` or ``didact.hotspot``.
  Writing there needs either a ``DROP NOT NULL`` (whose downgrade cannot be honoured once
  this feature has written rows, so the migration would stop being additive) or a new
  value on an enum ``exercises`` and ``exercise_attempts`` also depend on (irreversible in
  PostgreSQL).
* ``activity_states`` is keyed exactly right, ``(activity_id, user_id)``, and owned by the
  wrong side: its ``state`` column is an opaque draft the client writes through
  ``PUT /activities/{id}/state``. A counter that decides when an answer is disclosed
  cannot live in a row the client controls.

So: a small server-owned row of counters per learner and per activity, the shape
``learner_node_states`` already has one level up. Purely additive — one new table, no
existing column touched — and ``downgrade`` drops exactly what was created here. Every
counter starts at zero, which is the truth for every learner who has never been counted:
the first request after this deploy is their first countable attempt, and the only visible
consequence is that failures accumulated before it are not held against the new rule.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learner_activity_states",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "activity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("activity_definitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempts_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("failures_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("hints_used", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        # The reveal, and nothing about mastery next to it: `POST /complete` stamps
        # `completed_at` the same way, for the same reason.
        sa.Column("solution_revealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("attempts_count >= 0", name="ck_las_attempts"),
        sa.CheckConstraint("failures_count >= 0", name="ck_las_failures"),
        # A failure is an attempt, so one can never outnumber the other. The constraint is
        # cheap and it is the one thing that would catch an increment written on only one
        # of the two columns.
        sa.CheckConstraint(
            "failures_count <= attempts_count", name="ck_las_failures_within_attempts"
        ),
        sa.CheckConstraint("hints_used >= 0", name="ck_las_hints"),
        sa.UniqueConstraint("activity_id", "user_id", name="uq_las_learner"),
    )
    # Art. 17 erasure deletes by `user_id` across every personal table at once
    # (`LearnerProfileRepository.erase_user_data`), and this is now one of them.
    op.create_index("idx_las_user", "learner_activity_states", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_las_user", table_name="learner_activity_states")
    op.drop_table("learner_activity_states")
