"""Let a course be deleted with people in it: ``enrollments.course_id`` cascades.

Migration 0024 made two bookkeeping references to ``courses.id`` ``SET NULL`` and
deliberately left this one restrictive, because ``CourseService.delete`` refused a course
that had enrollments and the foreign key was the backstop for that product rule.

The rule is gone. An admin can delete any course they own, in any status, and the
safeguard moved from "you may not" to "you will be told exactly what this destroys, and
it will be recorded": the library shows the enrollment counts before the delete and asks
for the course title to be typed back when completed enrollments are involved, and
``CourseService.delete`` writes a ``course_deleted`` row into ``audit_log`` naming the
actor, the title, the status and both counts. With the rule gone the backstop only turns
an allowed action into a ``ForeignKeyViolation``, so this is the eleventh reference to
``courses.id`` to get an ``ON DELETE``, and the only one that had to be ``CASCADE``: an
enrollment without its course is not history, it is a broken row — the person's progress,
score and deadline all describe content that no longer exists.

Nothing references ``enrollments`` in turn, so the cascade stops here.

The constraint was created inline by ``op.create_table`` in 0001 and never named, so it
is looked up by column rather than spelled out — the same reason, and the same helper, as
in 0024. ``downgrade`` puts it back with no ``ON DELETE``, which is exactly what it was.

Revision ID: 0032
Revises: 0031
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "enrollments"
_COLUMN = "course_id"


def _fk_name() -> str:
    """The name of the ``courses.id`` foreign key on ``enrollments.course_id``."""
    inspector = sa.inspect(op.get_bind())
    for fk in inspector.get_foreign_keys(_TABLE):
        if fk["referred_table"] == "courses" and fk["constrained_columns"] == [_COLUMN]:
            name = fk.get("name")
            if name:
                return name
    raise RuntimeError(f"No courses.id foreign key found on {_TABLE}.{_COLUMN}")


def _recreate(ondelete: str | None) -> None:
    op.drop_constraint(_fk_name(), _TABLE, type_="foreignkey")
    op.create_foreign_key(
        f"fk_{_TABLE}_{_COLUMN}",
        _TABLE,
        "courses",
        [_COLUMN],
        ["id"],
        ondelete=ondelete,
    )


def upgrade() -> None:
    _recreate("CASCADE")


def downgrade() -> None:
    _recreate(None)
