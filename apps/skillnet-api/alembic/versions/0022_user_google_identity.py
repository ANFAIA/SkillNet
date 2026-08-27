"""Add ``users.google_sub``: the external identity behind "Sign in with Google".

Additive and nullable, so every existing password-only account is untouched and
reads as "no Google identity linked". The column stores Google's OIDC ``sub``
claim and not the email address: ``sub`` is stable and never reused, whereas an
email can be reassigned within a Workspace domain. Unique across the table —
one external identity maps to exactly one account.

See ``src/services/google_oauth.py`` for the matching rules per workspace mode.

Revision ID: 0022
Revises: 0021
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("google_sub", sa.String(), nullable=True))
    # Partial index: many rows are legitimately NULL, and a plain UNIQUE would be
    # fine in PostgreSQL (NULLs do not collide) but this also keeps the index small.
    op.create_index(
        "uq_users_google_sub",
        "users",
        ["google_sub"],
        unique=True,
        postgresql_where=sa.text("google_sub IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_users_google_sub", table_name="users")
    op.drop_column("users", "google_sub")
