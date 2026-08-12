"""Add the closed, versioned learner presentation preference bundle.

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFAULT = (
    r"""'{"version"\:1,"presentation"\:"balanced","detail"\:"standard","""
    r""""images"\:"when_useful"}'::jsonb"""
)


def upgrade() -> None:
    op.add_column(
        "learner_profiles",
        sa.Column(
            "learning_preferences",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text(_DEFAULT),
        ),
    )
    op.add_column(
        "learner_profiles",
        sa.Column(
            "personalization_revision",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "learner_node_states",
        sa.Column("pinned_personalization_revision", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("learner_node_states", "pinned_personalization_revision")
    op.drop_column("learner_profiles", "personalization_revision")
    op.drop_column("learner_profiles", "learning_preferences")
