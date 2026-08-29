"""node_feedback: drop the end-of-node feedback form and the table behind it

Revision ID: 0036
Revises: 0035
Create Date: 2026-08-29

``POST /nodes/{id}/feedback`` was the table's **only** writer, and nothing ever called it:
the React component that asked "how did this lesson go?" (`NodeFeedback.tsx`) existed but
was mounted by no screen, so no build of the SPA ever shipped a way to reach the endpoint.
The table is therefore empty by construction and this migration destroys no learner data.
The check was done by grep before writing it: one constructor in `src/routes/nodes.py`,
one import of that component, and it was the component importing its own hook.

What the column fed is the more interesting half. ``difficulty`` was the trigger of
``bajar_dificultad`` / ``subir_dificultad`` in ``learner_profile_service.evaluate_signals``,
and those two actions only turn into a prompt instruction inside ``build_ui_prompt`` — the
legacy render path. The episode path that actually serves production
(``build_episode_ui_prompt``) never reads ``_SIGNAL_RULES``. So even a populated table
would have changed nothing that a learner sees. That is the real reason this never worked,
and the thing to fix first if it comes back: see
``docs/design/future-lesson-feedback.md``.

**What is not being removed:** difficulty *inferred* from graded answers.
``MasteryEvidenceService`` still builds a ``NodeSignalContext`` on every answer from
``consecutive_failed`` / ``consecutive_correct`` and the prerequisite graph, and the other
three signals of §3.3 are untouched.

The downgrade rebuilds the table exactly as ``0005_dynamic_courses.py`` created it,
constraints and all. It cannot bring rows back, which costs nothing here for the reason
above.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("node_feedback")


def downgrade() -> None:
    op.create_table(
        "node_feedback",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.Uuid(), nullable=False),
        sa.Column("difficulty", sa.Text(), nullable=False),
        sa.Column("unclear", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["course_nodes.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "difficulty IN ('easy', 'ok', 'hard')", name="ck_node_feedback_difficulty"
        ),
        sa.UniqueConstraint("user_id", "node_id", name="uq_node_feedback_user_node"),
    )
