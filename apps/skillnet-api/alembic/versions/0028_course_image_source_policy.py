"""courses.image_source_policy: keep the document's own image, or rebuild it

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-27

``source_images`` (0026) kept the pictures that were inside the uploaded document and
0027 classified them (``screenshot`` | ``diagram`` | ``photo`` | ``unknown``). This
column is the per-course answer to what a lesson then does with one.

The rule is ``auto`` and it needs no setting: a screenshot is kept, because its
information is *where a control sits* and prose is strictly worse than the picture; a
diagram is rebuilt, because a conceptual drawing is usually better as interactive
SkillNet content than as a photograph of a drawing; and ``unknown`` is kept, because
nothing can be rebuilt from a description that was never made (which is every image on
a deployment with no ``VISION_MODEL``).

The two overrides are policy rather than judgement, which is exactly why a heuristic
cannot cover them: ``keep_original`` is "do not invent anything, show my material" —
a compliance requirement — and ``rebuild`` is "everything in our own visual language".

Additive and defaulted to ``'auto'``, so every existing course keeps the rule and no
render already in ``node_renders`` is invalidated by this landing (a course with no
source images contributes nothing to the render cache key at all). Shaped like
``0021_course_tutor_style`` — a PG enum plus one NOT NULL column with a server default.
The setting is **not** part of course creation; it is edited via ``PUT /courses/{id}``.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENUM_NAME = "course_image_source_policy"


def upgrade() -> None:
    image_source_policy = postgresql.ENUM(
        "auto", "keep_original", "rebuild", name=_ENUM_NAME, create_type=False
    )
    image_source_policy.create(op.get_bind())
    op.add_column(
        "courses",
        sa.Column(
            "image_source_policy",
            image_source_policy,
            nullable=False,
            server_default="auto",
        ),
    )


def downgrade() -> None:
    op.drop_column("courses", "image_source_policy")
    sa.Enum(name=_ENUM_NAME).drop(op.get_bind())
