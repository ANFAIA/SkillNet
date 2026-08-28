"""node_renders.prompt_version: which instructions produced this row

Revision ID: 0031
Revises: 0030
Create Date: 2026-08-28

``PROMPT_VERSION`` enters the ``cache_key`` (§3.4), so bumping it invalidates every
cached render at once. Invalidating is not deleting: the rows stay in the table,
unreachable forever, holding a ``ui_spec`` and a ``dialect`` each. Reclaiming them needs
a way to ask a row "were you generated under the version that is current now?", and until
this column there was none — ``cache_key`` is the ``sha256`` of the material, so the
version is inside the hash and cannot be read back out.

``catalog_version`` and ``library_version`` already record the other two halves of the
same question (which component catalogue the model was taught, which renderer drew the
result). This is the third and the one that was missing: which instructions.

Nullable and not back-filled, on purpose. ``NULL`` means "written by a build older than
this migration", which is the truth for every existing row and is exactly what
``src/services/render_retention.py`` treats as stale. The one-time cost of that reading
is that a render generated shortly before this deploy, under the version that is still
current, and never opened by anybody, is swept and regenerated on next demand — money,
never evidence, because the sweep also refuses any row something still points at.

``downgrade`` is a plain ``drop_column``: it loses only the column added here.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "node_renders",
        sa.Column("prompt_version", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("node_renders", "prompt_version")
