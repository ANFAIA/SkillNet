"""Let a draft course be deleted: ``SET NULL`` on the two FKs that only reference it.

``DELETE /courses/{id}`` has existed since 0001 and could not be used: three foreign keys
point at ``courses.id`` with no ``ondelete``, so Postgres raised ``ForeignKeyViolation``
and the route answered 500 instead of deleting. Two of them are bookkeeping references
that outlive the course they mention:

* ``generation_jobs.result_course_id`` — the audit trail of a generation run. Every v1
  course has one, and so does every course whose schema was proposed, so this FK alone
  turned "delete the draft that failed" into a 500 for most drafts. The job row is
  history and must survive; it just stops naming a course that no longer exists.
* ``chat_sessions.course_id`` — a tutor thread scoped to a course. The transcript is the
  learner's, not the course's, and the session degrades to a general one.

Both columns are already nullable, so ``SET NULL`` needs no data migration.

``enrollments.course_id`` is deliberately left restrictive. ``CourseService.delete``
refuses a course that has enrollments, and that refusal is the product rule: nobody's
progress disappears because an admin tidied the catalogue. The FK is the backstop that
keeps the rule true even if a future caller forgets it.

The constraints were created inline by ``op.create_table`` in 0001 and never named, so
their names are whatever Postgres generated. They are looked up by column rather than
spelled out, which also makes the migration correct on a database created before any
naming convention existed.

Revision ID: 0024
Revises: 0023
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, column) pairs that move to ON DELETE SET NULL, and back on downgrade.
_TARGETS = (
    ("generation_jobs", "result_course_id"),
    ("chat_sessions", "course_id"),
)


def _fk_name(table: str, column: str) -> str:
    """The name of the ``courses.id`` foreign key on ``table.column``."""
    inspector = sa.inspect(op.get_bind())
    for fk in inspector.get_foreign_keys(table):
        if fk["referred_table"] == "courses" and fk["constrained_columns"] == [column]:
            name = fk.get("name")
            if name:
                return name
    raise RuntimeError(f"No courses.id foreign key found on {table}.{column}")


def _recreate(ondelete: str | None) -> None:
    for table, column in _TARGETS:
        op.drop_constraint(_fk_name(table, column), table, type_="foreignkey")
        op.create_foreign_key(
            f"fk_{table}_{column}",
            table,
            "courses",
            [column],
            ["id"],
            ondelete=ondelete,
        )


def upgrade() -> None:
    _recreate("SET NULL")


def downgrade() -> None:
    _recreate(None)
