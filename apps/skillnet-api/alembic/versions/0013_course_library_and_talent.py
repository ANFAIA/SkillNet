"""Add flat course folders and course-completion skill provenance.

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "course_folders",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_course_folders_org_id", "course_folders", ["org_id"])
    op.create_index(
        "uq_course_folders_org_lower_name",
        "course_folders",
        ["org_id", sa.text("lower(name)")],
        unique=True,
    )
    op.add_column(
        "courses",
        sa.Column("folder_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_courses_folder_id",
        "courses",
        "course_folders",
        ["folder_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_courses_folder_id", "courses", ["folder_id"])


def downgrade() -> None:
    op.drop_index("ix_courses_folder_id", table_name="courses")
    op.drop_constraint("fk_courses_folder_id", "courses", type_="foreignkey")
    op.drop_column("courses", "folder_id")
    op.drop_index("uq_course_folders_org_lower_name", table_name="course_folders")
    op.drop_index("ix_course_folders_org_id", table_name="course_folders")
    op.drop_table("course_folders")
