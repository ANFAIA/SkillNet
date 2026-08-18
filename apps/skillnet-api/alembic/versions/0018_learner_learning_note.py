"""Learner learning-note: a per-learner free-text "how I like to learn" field.

A small, nullable free-text note on the learner profile where a person says HOW they like
lessons explained (metaphors, first principles, examples, tone). It steers only the FORM of
an explanation, never the facts, and partitions the render cache. See
``src/personalization/learning_note.py``.

Revision ID: 0018
Revises: 0017
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "learner_profiles",
        sa.Column("learning_note", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("learner_profiles", "learning_note")
