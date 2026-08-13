"""Per-course who may generate overviews (podcast, video, slides, infographic).

Revision ID: 0015
Revises: 0014
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    policy = postgresql.ENUM(
        "admin",
        "everyone",
        "selected",
        name="artifact_generate_policy",
        create_type=False,
    )
    policy.create(op.get_bind())
    op.add_column(
        "courses",
        sa.Column(
            "artifact_generate_policy",
            policy,
            nullable=False,
            server_default="admin",
        ),
    )
    op.create_table(
        "course_artifact_generators",
        sa.Column(
            "course_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index(
        "idx_course_artifact_generators_user",
        "course_artifact_generators",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_course_artifact_generators_user", table_name="course_artifact_generators")
    op.drop_table("course_artifact_generators")
    op.drop_column("courses", "artifact_generate_policy")
    sa.Enum(name="artifact_generate_policy").drop(op.get_bind())
