"""add course_skills join table

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "course_skills",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("skill_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("course_id", "skill_id", name="uq_course_skills_course_skill"),
    )
    op.create_index("idx_course_skills_course", "course_skills", ["course_id"])
    op.create_index("idx_course_skills_skill", "course_skills", ["skill_id"])


def downgrade() -> None:
    op.drop_index("idx_course_skills_skill", table_name="course_skills")
    op.drop_index("idx_course_skills_course", table_name="course_skills")
    op.drop_table("course_skills")
