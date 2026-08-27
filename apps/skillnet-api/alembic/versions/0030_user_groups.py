"""Named groups of people, their membership, and enrollment provenance.

Revision ID: 0030
Revises: 0029
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_groups",
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
    op.create_index("ix_user_groups_org_id", "user_groups", ["org_id"])
    # Same shape as `uq_course_folders_org_lower_name` (0013): one name per organization,
    # case-insensitively, so "Turno de tarde" and "turno de tarde" cannot both exist.
    op.create_index(
        "uq_user_groups_org_lower_name",
        "user_groups",
        ["org_id", sa.text("lower(name)")],
        unique=True,
    )

    op.create_table(
        "user_group_members",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("group_id", "user_id", name="uq_user_group_members_pair"),
    )
    op.create_index("ix_user_group_members_user_id", "user_group_members", ["user_id"])

    # Provenance. Nullable and SET NULL: deleting a group must never delete training,
    # and every row that exists today predates groups, so NULL is the honest value.
    op.add_column(
        "enrollments",
        sa.Column("source_group_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_enrollments_source_group_id",
        "enrollments",
        "user_groups",
        ["source_group_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_enrollments_source_group_id", "enrollments", ["source_group_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_enrollments_source_group_id", table_name="enrollments")
    op.drop_constraint("fk_enrollments_source_group_id", "enrollments", type_="foreignkey")
    op.drop_column("enrollments", "source_group_id")
    op.drop_index("ix_user_group_members_user_id", table_name="user_group_members")
    op.drop_table("user_group_members")
    op.drop_index("uq_user_groups_org_lower_name", table_name="user_groups")
    op.drop_index("ix_user_groups_org_id", table_name="user_groups")
    op.drop_table("user_groups")
