"""add skill_categories, skills, user_skills, and api_keys tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Enum ---
    # `postgresql.ENUM` and not `sa.Enum`: only the dialect type honours
    # `create_type=False` below. `sa.Enum` drops the flag when it adapts itself to the
    # postgres dialect, so `create_table("user_skills")` re-issued `CREATE TYPE
    # skill_level` and the whole upgrade died with DuplicateObjectError on a clean
    # database. Measured against pgvector/pgvector:pg16.
    skill_level = postgresql.ENUM("low", "medium", "high", name="skill_level")
    skill_level.create(op.get_bind(), checkfirst=True)

    # --- skill_categories ---
    op.create_table(
        "skill_categories",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.UniqueConstraint("org_id", "name", name="uq_skill_categories_org_name"),
    )

    # --- skills ---
    op.create_table(
        "skills",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["skill_categories.id"]),
        sa.UniqueConstraint("org_id", "name", name="uq_skills_org_name"),
    )
    op.create_index("idx_skills_org", "skills", ["org_id"])

    # --- user_skills ---
    op.create_table(
        "user_skills",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("skill_id", sa.Uuid(), nullable=False),
        sa.Column(
            "level",
            postgresql.ENUM("low", "medium", "high", name="skill_level", create_type=False),
            nullable=False,
            server_default="low",
        ),
        sa.Column("source", sa.String(), nullable=False, server_default="checkpoint"),
        sa.Column("last_assessed_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"]),
        sa.UniqueConstraint("user_id", "skill_id", name="uq_user_skills_user_skill"),
    )
    op.create_index("idx_user_skills_user", "user_skills", ["user_id"])
    op.create_index("idx_user_skills_skill", "user_skills", ["skill_id"])

    # --- api_keys ---
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("key_hash", sa.String(), nullable=False),
        sa.Column("scopes", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
    )
    op.create_index("idx_api_keys_org", "api_keys", ["org_id"])
    op.create_index("idx_api_keys_hash", "api_keys", ["key_hash"])


def downgrade() -> None:
    op.drop_index("idx_api_keys_hash", table_name="api_keys")
    op.drop_index("idx_api_keys_org", table_name="api_keys")
    op.drop_table("api_keys")

    op.drop_index("idx_user_skills_skill", table_name="user_skills")
    op.drop_index("idx_user_skills_user", table_name="user_skills")
    op.drop_table("user_skills")

    op.drop_index("idx_skills_org", table_name="skills")
    op.drop_table("skills")

    op.drop_table("skill_categories")

    postgresql.ENUM(name="skill_level").drop(op.get_bind(), checkfirst=True)
