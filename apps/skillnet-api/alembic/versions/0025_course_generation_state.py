"""Add ``courses.generation_state``: whether the course finished being created.

A v2 course is only servable once ``POST /schema/validate`` has run, and until this
revision the wizard ran that step from the browser tab. A tab that was closed,
reloaded or killed between "create the course" and "validate the schema" left the row
behind with ``status='draft'`` and ``schema_status='draft'`` — indistinguishable from a
draft somebody saved on purpose, because nothing recorded that a creation run had been
started and had died. The admin saw "0 modulos" and no way to act on it.

Three additive, defaulted columns close that gap:

* ``generation_state`` — ``idle`` (nobody is creating this), ``in_progress`` (a run owns
  it), ``failed`` (a run died and said why), ``complete`` (the run validated it).
* ``generation_error`` — a short, safe sentence. Never a raw exception: the same
  discipline as ``src/services/media/jobs.classify_failure``, which exists because a
  provider's exception text is unreadable at best and leaks deployment details at worst.
* ``generation_failed_at`` — when the run died, so a stale ``failed`` can be told from a
  fresh one.

``idle`` is the default, so every existing row keeps exactly the meaning it has today
and no screen changes for courses created before this revision.

Revision ID: 0025
Revises: 0024
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENUM_NAME = "course_generation_state"


def upgrade() -> None:
    generation_state = postgresql.ENUM(
        "idle",
        "in_progress",
        "failed",
        "complete",
        name=_ENUM_NAME,
        create_type=False,
    )
    generation_state.create(op.get_bind())
    op.add_column(
        "courses",
        sa.Column(
            "generation_state",
            generation_state,
            nullable=False,
            server_default="idle",
        ),
    )
    op.add_column(
        "courses",
        sa.Column("generation_error", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "courses",
        sa.Column(
            "generation_failed_at", sa.DateTime(timezone=True), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("courses", "generation_failed_at")
    op.drop_column("courses", "generation_error")
    op.drop_column("courses", "generation_state")
    sa.Enum(name=_ENUM_NAME).drop(op.get_bind())
