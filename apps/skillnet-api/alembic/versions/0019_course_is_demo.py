"""Add ``courses.is_demo``: a pre-baked onboarding demo course flag.

Additive and defaulted, so every existing course reads as ``false`` and the v1/v2
delivery decision is untouched. See ``src/services/org_demo_seed.py``.

Revision ID: 0019
Revises: 0018
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "courses",
        sa.Column(
            "is_demo",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("courses", "is_demo")
