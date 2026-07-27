"""documents.origin — tell an uploaded source apart from one the model wrote

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-27

Creating a course "desde cero" synthesises its source document instead of asking for
an upload. Everything downstream — the v1 generation pipeline, the v2 schema graph, the
node runtime, the tutor's retrieval — then treats it exactly like any other document,
which is the whole point of doing it this way: one new path at the front, no special
cases anywhere else.

That only stays honest if the difference is visible. A synthesised "Manual de
alergenos" carries the model's knowledge, not the company's policy, and a compliance
course whose source silently turned out to be invented is the failure this product
exists to avoid. So it is a column, not a naming convention.

Additive and defaulted: every existing row is ``uploaded``, which is what it is, and no
v1 code path reads the column.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VALUES = ("uploaded", "generated")


def upgrade() -> None:
    bind = op.get_bind()
    # `postgresql.ENUM` and not `sa.Enum`: only the dialect type honours
    # `create_type=False`, which is what migration 0003 got wrong and what made a
    # from-scratch upgrade impossible until 2026-07-27.
    postgresql.ENUM(*_VALUES, name="document_origin").create(bind, checkfirst=True)
    op.add_column(
        "documents",
        sa.Column(
            "origin",
            postgresql.ENUM(*_VALUES, name="document_origin", create_type=False),
            nullable=False,
            server_default="uploaded",
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "origin")
    postgresql.ENUM(*_VALUES, name="document_origin").drop(
        op.get_bind(), checkfirst=True
    )
