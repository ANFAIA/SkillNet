"""learner_node_states.completed_at: the learner finished the node, which is not mastery

Revision ID: 0029
Revises: 0028
Create Date: 2026-08-27

The reported symptom was "a finished course shows 0% and never turns green", and the
cause is that the table had no column for the thing the learner actually did.

Progress on a dynamic course is ``done_nodes / nodes`` and "done" meant ``state =
'mastered'``. ``mastered`` is only reachable through rule 6 of §7.3, which requires
``consecutive_correct >= FADING_STREAK`` (3) on **graded** items. An expository node has
no graded item at all, so it can never leave ``not_started`` — no matter how completely
it was read — and an episode currently serves one graded item per node, so a streak of
three is out of reach even where items exist. The consequence is arithmetic: a course of
five expository nodes read end to end reports 0/5.

``first_seen_at`` (0011) cannot stand in for this. It is stamped when the render is
*served*, i.e. when the node is opened, so it answers "how deep did they get" and marks
the node in progress the instant it appears on screen. Finishing is a different event,
with a different writer (``POST /nodes/{id}/complete``), and conflating the two would
report a node as done the moment it was opened.

Nullable, no default, and no other column touched. That is what makes it safe on a
database with live enrollments: every existing row keeps meaning exactly what it meant
(``NULL`` = "we never recorded a finish", which is the truth for every row written before
this), nothing is back-filled from a guess, and ``downgrade`` is a plain ``drop_column``
that loses only the column this migration added. ``timestamptz`` for consistency with
``first_seen_at`` / ``mastered_at`` / ``waived_at`` on the same table.

Deliberately **not** an extra value of the ``node_state`` enum. ``state`` is the mastery
ladder of §7.3 and a single scale cannot hold two independent facts: somebody can have
finished a node and still not have demonstrated it, and somebody can master a node
without reaching its last screen. A second column keeps both readable; a widened enum
would have to pick one and lose the other.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "learner_node_states",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("learner_node_states", "completed_at")
