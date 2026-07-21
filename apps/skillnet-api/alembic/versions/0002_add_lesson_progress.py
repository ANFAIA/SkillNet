"""add lesson_progress table for tracking per-lesson completion

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lesson_progress",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("lesson_id", sa.Uuid(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "lesson_id"),
    )
    op.create_index("idx_lesson_progress_user", "lesson_progress", ["user_id"])
    op.create_index("idx_lesson_progress_lesson", "lesson_progress", ["lesson_id"])


def downgrade() -> None:
    op.drop_index("idx_lesson_progress_lesson", table_name="lesson_progress")
    op.drop_index("idx_lesson_progress_user", table_name="lesson_progress")
    op.drop_table("lesson_progress")
