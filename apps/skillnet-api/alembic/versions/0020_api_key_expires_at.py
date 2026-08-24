"""Add ``api_keys.expires_at``: optional expiry for external API keys.

The data model documented in ``docs/design/mcp-external-api.md`` (8.1.1) always
included ``expires_at``, but the column never made it into migration 0003. Nullable
and additive: existing keys read as "never expires" (``null``), matching the
documented default. See ``src/routes/ext/auth.py`` for the enforcement.

Revision ID: 0020
Revises: 0019
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column("expires_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_keys", "expires_at")
