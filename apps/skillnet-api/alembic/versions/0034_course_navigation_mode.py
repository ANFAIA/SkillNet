"""Add ``courses.navigation_mode`` (free/sequential): who decides the order of lessons.

Additive and defaulted to ``'free'``, which is precisely what every course already did —
the whole node list open, walked in any order — so **this migration rewrites no row and
changes no behaviour**. A course only becomes sequential when somebody chooses it.

Sequential opens a lesson when the previous one is *finished* rather than *mastered*.
That is deliberate and it is what makes the mode safe: the prerequisite padlocks removed
just before this compared against ``mastered``, unreachable on an expository node, so the
next lesson stayed shut for ever. The rule lives in ``src/services/node_progression.py``,
which is the only place that decides it; ``POST /nodes/{id}/complete`` enforces it.

Shaped exactly like ``0021_course_tutor_style``: a named enum type created beside the
column, editable afterwards via ``PUT /courses/{id}``.

Revision ID: 0034
Revises: 0033
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENUM_NAME = "course_navigation_mode"


def upgrade() -> None:
    navigation_mode = postgresql.ENUM(
        "free", "sequential", name=_ENUM_NAME, create_type=False
    )
    navigation_mode.create(op.get_bind())
    op.add_column(
        "courses",
        sa.Column(
            "navigation_mode",
            navigation_mode,
            nullable=False,
            server_default="free",
        ),
    )


def downgrade() -> None:
    op.drop_column("courses", "navigation_mode")
    sa.Enum(name=_ENUM_NAME).drop(op.get_bind())
