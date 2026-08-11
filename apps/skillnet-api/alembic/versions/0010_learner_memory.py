"""learner_profiles.memory_md: the per-learner narrative memory ("user.md")

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-11

Two additive, nullable columns on ``learner_profiles`` — the sectioned markdown notebook
(``memory_md``) and its last-write timestamp (``memory_updated_at``). It is the
human-readable, agent-maintained complement to the numeric ``format_vector`` /
``tutor_notes`` state: how the learner uses the app, in prose, read back by the tutor to
personalize. See ``docs/learner-memory.md``.

Additive and reversible with no data loss: it touches nothing ``0001..0009`` created and
the down-migration is a clean ``DROP COLUMN``. ``memory_md`` starts ``NULL`` for every
existing row, which :class:`LearnerMemoryService` reads as "empty notebook".
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "learner_profiles",
        sa.Column("memory_md", sa.Text(), nullable=True),
    )
    op.add_column(
        "learner_profiles",
        sa.Column("memory_updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("learner_profiles", "memory_updated_at")
    op.drop_column("learner_profiles", "memory_md")
