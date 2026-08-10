"""media_artifacts: the shared spine for NotebookLM-style rich media

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-10

One table plus two enum types. Every rich artifact (podcast, slide deck, infographic,
narrated-slides video, mind map, report, cover image) is a row here, generated
asynchronously and served the same way — the primitive the whole media roadmap (§2, §3
build-order item #1) stands on.

The two ``CREATE TYPE`` statements go first and out of the table definition, the same
shape ``0005`` uses: ``postgresql.ENUM(..., name=...).create(bind, checkfirst=True)`` up
front, then the column references the type with ``create_type=False`` so the table build
does not try to emit ``CREATE TYPE`` a second time. ``checkfirst=True`` keeps the upgrade
re-runnable after a half-applied migration.

Additive: it touches nothing that ``0001..0008`` created. ``document_chunks`` and its
vector column are untouched, so unlike ``0008`` this migration loses no data and the
down-migration is a clean drop.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The two enum types this table introduces. Literal values, matching the ``str`` enums in
#: ``src/models/media_artifact.py`` — the model's ``values_callable`` emits exactly these.
_KIND = (
    "podcast",
    "slides",
    "infographic",
    "video",
    "mindmap",
    "report",
    "cover_image",
)
_STATUS = ("pending", "running", "done", "error")


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Every CREATE TYPE first (see module docstring; mirrors 0005).
    postgresql.ENUM(*_KIND, name="media_kind").create(bind, checkfirst=True)
    postgresql.ENUM(*_STATUS, name="media_artifact_status").create(
        bind, checkfirst=True
    )

    # 2. The table. Enums referenced with create_type=False so the build does not re-emit
    #    CREATE TYPE.
    op.create_table(
        "media_artifacts",
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
            nullable=True,
        ),
        sa.Column(
            "kind",
            postgresql.ENUM(*_KIND, name="media_kind", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                *_STATUS, name="media_artifact_status", create_type=False
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "spec_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("asset_path", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
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
    )

    # 3. Indexes: newest-first per course, status scans, and the dedup lookup by hash.
    op.create_index(
        "idx_media_artifacts_course",
        "media_artifacts",
        ["course_id", sa.text("created_at DESC")],
    )
    op.create_index("idx_media_artifacts_status", "media_artifacts", ["status"])
    op.create_index(
        "idx_media_artifacts_content_hash", "media_artifacts", ["content_hash"]
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_index("idx_media_artifacts_content_hash", table_name="media_artifacts")
    op.drop_index("idx_media_artifacts_status", table_name="media_artifacts")
    op.drop_index("idx_media_artifacts_course", table_name="media_artifacts")
    op.drop_table("media_artifacts")
    postgresql.ENUM(*_STATUS, name="media_artifact_status").drop(bind, checkfirst=True)
    postgresql.ENUM(*_KIND, name="media_kind").drop(bind, checkfirst=True)
