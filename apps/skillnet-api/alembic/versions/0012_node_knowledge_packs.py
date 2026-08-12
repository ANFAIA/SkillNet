"""Persist immutable, grounded learning dossiers for course-node snapshots.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS = ("pending", "ready", "review_required", "stale", "failed")


def upgrade() -> None:
    bind = op.get_bind()
    postgresql.ENUM(*_STATUS, name="node_knowledge_pack_status").create(
        bind, checkfirst=True
    )
    op.create_table(
        "node_knowledge_packs",
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
        sa.Column(
            "course_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "node_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("course_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_fingerprint", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("generator_version", sa.Text(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                *_STATUS, name="node_knowledge_pack_status", create_type=False
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("markdown", sa.Text(), nullable=True),
        sa.Column(
            "atoms",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "pack_payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "provenance",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("markdown_hash", sa.Text(), nullable=True),
        sa.Column("atoms_hash", sa.Text(), nullable=True),
        sa.Column("pack_hash", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "node_id",
            "source_fingerprint",
            "generator_version",
            name="uq_node_knowledge_packs_snapshot",
        ),
        sa.CheckConstraint(
            "status NOT IN ('ready', 'review_required') OR ("
            "markdown IS NOT NULL AND markdown_hash IS NOT NULL "
            "AND pack_hash IS NOT NULL AND jsonb_typeof(pack_payload) = 'object')",
            name="ck_node_knowledge_packs_ready_payload",
        ),
    )
    op.create_index(
        "idx_node_knowledge_packs_node",
        "node_knowledge_packs",
        ["node_id", sa.text("created_at DESC")],
    )
    op.create_index("idx_node_knowledge_packs_status", "node_knowledge_packs", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_index("idx_node_knowledge_packs_status", table_name="node_knowledge_packs")
    op.drop_index("idx_node_knowledge_packs_node", table_name="node_knowledge_packs")
    op.drop_table("node_knowledge_packs")
    postgresql.ENUM(*_STATUS, name="node_knowledge_pack_status").drop(bind, checkfirst=True)
