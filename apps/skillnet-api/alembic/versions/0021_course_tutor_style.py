"""Add ``courses.tutor_style`` (socratic/direct): a per-course tutor persona switch.

Additive and defaulted to ``'socratic'``, so every existing course keeps today's
tutor behavior. Auto-detected by the schema designer at creation
(``src/agents/schema/nodes.py``), editable afterward via ``PUT /courses/{id}``.
See ``src/llm/prompts/tutor.py`` for where the value changes the system prompt.

Revision ID: 0021
Revises: 0020
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021"
down_revision: str | None = "0020b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENUM_NAME = "course_tutor_style"


def upgrade() -> None:
    tutor_style = postgresql.ENUM(
        "socratic", "direct", name=_ENUM_NAME, create_type=False
    )
    tutor_style.create(op.get_bind())
    op.add_column(
        "courses",
        sa.Column(
            "tutor_style",
            tutor_style,
            nullable=False,
            server_default="socratic",
        ),
    )


def downgrade() -> None:
    op.drop_column("courses", "tutor_style")
    sa.Enum(name=_ENUM_NAME).drop(op.get_bind())
