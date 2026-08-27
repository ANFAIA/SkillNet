"""source_images: keep the pictures that were already inside the uploaded document

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-27

Ingestion has decoded the images embedded in an uploaded PDF since Phase 5 and thrown
every one of them away: the decoder handed the bytes to a vision model, the description
went into the section text, and the bytes were garbage collected. With ``VISION_MODEL``
unset — the default — not even that happened. So the customer's own wiring diagram, form
or machine photo left with the request that carried it in, and a course built on that
document could only ever illustrate itself with something a model invented.

This table is where they live from now on. One row per image kept, carrying the
provenance a caption needs (``document_id`` + ``page`` + ``heading``, the same three
fields a passage citation prints) and the deterministic junk verdict ``is_decorative``,
so the logo that repeats on every page header is recorded and marked rather than either
shown or silently dropped. ``description`` is nullable because storing the bytes needs no
model at all — only the caption does.

Additive: one table, no enum types, and nothing that ``0001..0025`` created is touched.
The ``ON DELETE CASCADE`` on ``document_id`` is what makes ``DELETE /documents/{id}``
complete — the rows go with the document, and the service removes their files.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_images",
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
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # 1-based, like ParsedSection.page_start and like the "pag. N" a citation prints.
        sa.Column("page", sa.Integer(), nullable=False),
        # Heading of the section covering that page; empty when the document has none.
        sa.Column("heading", sa.String(), nullable=False, server_default=""),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("asset_path", sa.Text(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("bytes", sa.Integer(), nullable=False),
        # NULL whenever no vision model was configured — which is the default.
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_decorative",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "extracted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # The listing every consumer performs: this document's images, in reading order.
    op.create_index("idx_source_images_document", "source_images", ["document_id", "page"])
    # The dedup/lookup key, and what the asset route rebuilds its file path from.
    op.create_index("idx_source_images_content_hash", "source_images", ["content_hash"])


def downgrade() -> None:
    op.drop_index("idx_source_images_content_hash", table_name="source_images")
    op.drop_index("idx_source_images_document", table_name="source_images")
    op.drop_table("source_images")
