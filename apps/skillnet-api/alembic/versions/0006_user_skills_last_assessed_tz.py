"""make user_skills.last_assessed_at timezone-aware

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-27

``user_skills`` came from 0003, before the codebase settled on ``timestamptz`` for
every timestamp it writes from Python — v2 declares ``DateTime(timezone=True)`` on all
28 of its datetime columns. The column was left as ``timestamp without time zone``,
but both writers hand it an **aware** value:

* ``SkillService.record_mastery`` (§3.3, the mastery -> ``user_skills`` bridge), and
* ``EnrollmentService._grant_course_skills`` (v1 course completion).

asyncpg refuses that combination outright — ``DataError: can't subtract offset-naive
and offset-aware datetimes`` — so *raising* an existing skill row crashed the request.
It survived until now because only the UPDATE branch is affected: the INSERT branches
either omit the column or are the one place that let the server default fill it, so a
learner who had never been assessed on the skill went through fine and a learner who
had did not.

``AT TIME ZONE 'UTC'`` is exact rather than merely conventional here: the only values
in the column were written by the ``now()`` server default, which Postgres stored in
the server's ``TimeZone``, and the deployment runs ``Etc/UTC``.

Only ``last_assessed_at`` is converted. The other seven naive columns of 0003
(``updated_at``/``created_at`` on this table, ``skills``, ``skill_categories``,
``api_keys.created_at``) are never assigned an aware value from Python — they are
filled by ``now()``/``onupdate`` server-side, and ``api_keys.last_used_at`` is written
with a naive ``utcnow()`` — so converting them would be churn, not a fix.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "user_skills",
        "last_assessed_at",
        type_=sa.DateTime(timezone=True),
        existing_type=sa.DateTime(),
        existing_nullable=False,
        existing_server_default=sa.text("now()"),
        postgresql_using="last_assessed_at AT TIME ZONE 'UTC'",
    )


def downgrade() -> None:
    op.alter_column(
        "user_skills",
        "last_assessed_at",
        type_=sa.DateTime(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        existing_server_default=sa.text("now()"),
        postgresql_using="last_assessed_at AT TIME ZONE 'UTC'",
    )
