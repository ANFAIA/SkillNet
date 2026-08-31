"""Add ``courses.language``: what language a course is written in, and answers in.

Additive and defaulted to ``'es'``, which is what every existing course already is, so
**this migration rewrites no row and changes no behaviour**. A course only becomes
English when somebody asks for one.

It exists because the language was until now inferred, once, from the source material
("write in the same language as the source", in half a dozen prompts). That holds while
the course is being created and stops holding immediately afterwards: rendering a screen
for a learner, answering as the tutor, grading an open answer and explaining a clicked
term all happen later, with no source document in hand. Without a stored answer an
English course drifts back into Spanish the moment the pipeline finishes — which is
exactly what a reviewer saw on the public demo, an English interface wrapped around
Spanish lessons.

``Text`` rather than a named enum, unlike ``0034_course_navigation_mode`` and
``0021_course_tutor_style``, and matching ``term_explanations.language``, which is the
only other language column in the schema: the set of supported languages is a product
decision that will grow, and growing an enum in Postgres means an ``ALTER TYPE`` in a
migration for what should be one row in a table of names. The allowed values are
enforced where they are read, in ``src.core.language``.

Note for whoever adds the third language: ``services/cache_key.py`` includes this value
in the render cache material, so courses in different languages cannot collide on a
cached screen. That is a property of the key, not of this column, but it is the reason
this column can be trusted.

Revision ID: 0037
Revises: 0036
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "courses",
        sa.Column(
            "language",
            sa.Text(),
            nullable=False,
            server_default="es",
        ),
    )


def downgrade() -> None:
    op.drop_column("courses", "language")
