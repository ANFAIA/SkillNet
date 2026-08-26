"""Add ``media_artifacts.error_code``: a stable code beside the failure message.

Until now a failed generation stored ``f"{type(exc).__name__}: {exc}"`` in ``error`` and
showed it to whoever asked — a provider's raw exception text, unreadable to a learner and
capable of carrying an endpoint, a model name or an account identifier out of the
deployment. The message is now short, safe and English, and the machine-readable half
moves here so the client can key its own wording off the code instead of parsing prose.

Additive and nullable: every existing row reads as "a failure with no code", which is what
it is. See ``src/services/media/jobs.classify_failure`` for the values.

Revision ID: 0023
Revises: 0022
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "media_artifacts", sa.Column("error_code", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("media_artifacts", "error_code")
