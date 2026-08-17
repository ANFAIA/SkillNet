"""Deployment workspace mode: organization (default) or individual.

A stable per-deployment capability, not inferred from user count. Existing
deployments upgrade to ``organization`` so nothing changes for them. See
``docs/design/audience-modes.md``.

Revision ID: 0017
Revises: 0016
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    mode = postgresql.ENUM(
        "organization",
        "individual",
        name="workspace_mode",
        create_type=False,
    )
    mode.create(op.get_bind())
    op.add_column(
        "organizations",
        sa.Column(
            "workspace_mode",
            mode,
            nullable=False,
            server_default="organization",
        ),
    )


def downgrade() -> None:
    op.drop_column("organizations", "workspace_mode")
    sa.Enum(name="workspace_mode").drop(op.get_bind())
