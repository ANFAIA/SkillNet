"""source_images.kind: what the picture IS, because the rendering decision is made from it

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-27

``0026`` gave an image a ``description`` and nothing else, and the vision prompt behind
it asked for "2-3 sentences describing what it shows". That is a caption: enough to make
the image findable by RAG, not enough to do anything with. The product now has to decide,
per image, between two incompatible treatments — rebuild what the image taught as
interactive content, or keep the original bytes and show them — and prose cannot be asked
that question after the fact.

So the verdict becomes a column. The distinction that carries the decision is
**screenshot vs everything else**: a screenshot's information is *spatial* (which corner
the button sits in), and any prose rewrite of it is strictly worse than the picture,
while a diagram or a photo can usually be re-expressed as something a learner can touch.

Values, as free text rather than a PostgreSQL enum:

* ``screenshot`` — a user-interface capture.
* ``diagram`` — flowchart, schema, conceptual drawing.
* ``photo`` — a real thing: a machine, a place, a paper document.
* ``unknown`` — nobody looked. ``VISION_MODEL`` is unset by default, and then there is
  no description and no classification at all; a decorative image is never described
  either. Downstream ``unknown`` reads exactly like ``screenshot``: cannot be rebuilt,
  keep the original. That is the safe direction — keeping an image that could have been
  rebuilt costs a little screen space, whereas rebuilding one that should have been kept
  silently drops what the manual was actually saying.

No ``CREATE TYPE`` and no ``CHECK``: the vocabulary is expected to grow (a table, a
chart, a form scan are all plausibly worth their own treatment), the write path is the
only writer and it normalises through :class:`src.models.source_image.SourceImageKind`,
and an unrecognised value from a model degrades to ``unknown`` rather than raising. A
native enum would turn each new kind into a migration *and* an ``ALTER TYPE``, and would
make this same column impossible to widen from a hotfix.

Additive: one column, ``NOT NULL`` with a server default, so every row ``0026`` already
wrote reads as ``unknown`` — which is what it is, since nothing classified them.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "source_images",
        sa.Column(
            "kind",
            sa.String(length=32),
            nullable=False,
            server_default="unknown",
        ),
    )


def downgrade() -> None:
    op.drop_column("source_images", "kind")
