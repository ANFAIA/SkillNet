"""Add server-owned declarative activity definitions.

Revision ID: 0014
Revises: 0013
"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create the PostgreSQL type once, then reference it from the table without
    # asking SQLAlchemy's table DDL to emit a second CREATE TYPE.
    family = postgresql.ENUM(
        "assessment",
        "artifact",
        "media",
        "simulation",
        "execution",
        name="activity_family",
        create_type=False,
    )
    family.create(op.get_bind())
    op.create_table(
        "activity_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("course_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_render_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("node_renders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_knowledge_pack_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("node_knowledge_packs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("definition_key", sa.Text(), nullable=False), sa.Column("component_id", sa.Text(), nullable=False),
        sa.Column("family", family, nullable=False), sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("public_definition", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("private_definition", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("required_ports", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("provenance", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("version > 0", name="ck_activity_definitions_version"),
        sa.UniqueConstraint("org_id", "definition_key", "version", name="uq_activity_definition_version"),
    )
    op.create_index("idx_activity_definitions_node", "activity_definitions", ["node_id"])
    op.create_index("idx_activity_definitions_component", "activity_definitions", ["component_id"])
    op.create_table(
        "activity_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("activity_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("state", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("activity_id", "user_id", name="uq_activity_states_learner"),
    )
    op.create_index("idx_activity_states_user", "activity_states", ["user_id"])


def downgrade() -> None:
    op.drop_table("activity_states")
    op.drop_table("activity_definitions")
    sa.Enum(name="activity_family").drop(op.get_bind())
