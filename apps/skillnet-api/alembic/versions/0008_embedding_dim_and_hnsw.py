"""document_chunks.embedding at a pinned dimension, and an HNSW index

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-04

Two changes in the same migration because both force the index to be rebuilt, and
splitting them would cost two rebuilds of the same index on the same table.

## The dimension, and why it is pinned here

Changing embedding provider changes the vector dimension, and there is no possible
conversion: a 384-component vector and a 768-component one do not describe the same
space, so they cannot be cast, truncated or padded. The column is **recreated** and the
chunks are re-ingested. That is honest: changing model invalidates every stored
embedding anyway, and faking a data migration would only leave old-model vectors
indistinguishable from the new ones.

``0001_initial.py`` wrote ``Vector(settings.EMBEDDING_DIMENSIONS)``, that is, it let an
environment variable decide the schema. **That is not repeated here, and not out of
taste: it was tried and it broke.** The first version of this migration read the
setting, and running the integration suite was enough to corrupt the database:
``test_migration_0005`` does upgrade -> downgrade -> upgrade, the downgrade came through
here, and the next upgrade re-read ``EMBEDDING_DIMENSIONS`` — which in a pytest run on
the host is the default, because ``SettingsConfigDict(env_file=".env")`` resolves
relative to the process directory and never sees the repository-root ``.env`` that
docker-compose reads. Result: the column back to 384, the corpus's 17 chunks deleted,
and not a single red test to say so.

A schema that depends on the environment cannot be reasoned about either: ``alembic
current`` stops being enough to know what is in the database, and a production dump does
not fit a development box configured differently.

So **the schema** dictates the dimension, and the model adapts. That is the right
direction for the dependency and it is how any real vector deployment works: you do not
change embedding dimension by editing an environment variable. The
``EMBEDDING_DIMENSIONS`` default in ``src/config.py`` goes up to 768 in the same commit
to match, along with the default model — ``multilingual-e5-base``, 768 dims, same family
as the previous one so the ``query:`` / ``passage:`` prefix logic still applies.

## The index

``0001_initial`` created ``ivfflat ... WITH (lists = 10)``. IVFFlat partitions the space
into lists and only looks at a few of them per query, so its recall depends on ``lists``
being sized to the row count (the usual rule is ``rows/1000``) and on the index having
been built **over representative data**: on an almost empty table the centroids mean
nothing. With 17 rows, `lists = 10` is not a choice but an accident.

HNSW is not trained: it builds an incremental navigable graph, gives better recall at
equal latency on small and medium corpora, and has no parameter to retune every time the
table grows by an order of magnitude. In exchange it takes more space and builds more
slowly, which is the right trade for a table that is read on every question and written
only when a document is ingested.

``vector_cosine_ops`` stays: ``similarity_search`` orders by ``cosine_distance``, and an
index with a different operator class simply would not be used.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Literals, never `settings`. See the docstring: reading it from the environment made the
#: test suite itself revert the schema and delete the corpus without a single red failure.
_DIMENSIONS = 768
_OLD_DIMENSIONS = 384
_INDEX = "idx_chunks_embedding"


def _swap_embedding_column(dimensions: int, index_sql: str) -> None:
    """Empty the chunks, recreate the column at ``dimensions``, and rebuild the index.

    **The chunks are deleted, not kept with a NULL embedding.** The column is ``NOT NULL``
    in ``DocumentChunk``, so leaving empty rows would force the model to be relaxed; but
    above all, a chunk with a NULL embedding still comes out of ``similarity_search`` —
    ``cosine_distance`` over NULL yields NULL and sorts last — so the search would return
    rows with no vector as if they were results. Better not to have them.

    Losing them breaks nothing as long as they are re-ingested: a document with
    ``full_text`` and no chunks is a legitimate state that the ladder in
    ``src/services/retrieval.py`` already handles, and it falls to the lexical rung or to
    the whole document.
    """
    op.execute(f"DROP INDEX IF EXISTS {_INDEX};")
    op.execute("DELETE FROM document_chunks;")
    op.drop_column("document_chunks", "embedding")
    op.add_column(
        "document_chunks",
        sa.Column("embedding", Vector(dimensions), nullable=False),
    )
    op.execute(index_sql)


def upgrade() -> None:
    _swap_embedding_column(
        _DIMENSIONS,
        f"CREATE INDEX {_INDEX} ON document_chunks USING hnsw (embedding vector_cosine_ops);",
    )


def downgrade() -> None:
    _swap_embedding_column(
        _OLD_DIMENSIONS,
        f"CREATE INDEX {_INDEX} ON document_chunks "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);",
    )
