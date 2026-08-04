"""Document chunk model (RAG with pgvector)."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, ForeignKey, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.document import Document


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    #: ``Vector()`` sin dimension, a proposito: la dimension la manda **la base**.
    #:
    #: Antes era ``Vector(settings.EMBEDDING_DIMENSIONS)``, y eso ponia la dependencia al
    #: reves — un ajuste de entorno describiendo una columna que ya existe. Con dos
    #: fuentes de verdad para el mismo numero, la que se lee en Python puede no ser la
    #: que Postgres aplica, y el desajuste solo aparece al insertar. La migracion 0008
    #: fija ``vector(768)`` y aqui no se repite el numero.
    #:
    #: No afecta al DDL porque nadie llama a ``create_all``: las migraciones son las
    #: unicas que crean esquema. Y no relaja ninguna validacion — Postgres sigue
    #: rechazando un vector del tamano equivocado, que es donde debe comprobarse.
    #: ``check_embedding_dimensions`` compara ambos al arrancar para que el fallo se vea
    #: antes de ingerir nada.
    embedding: Mapped[list[float]] = mapped_column(Vector(), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # `metadata` is reserved on declarative classes, so map the column explicitly.
    chunk_metadata: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    #: Spanish full-text index of ``content``, maintained by Postgres.
    #:
    #: The column and its GIN index have existed since the migration that created this
    #: table; what did not exist was any query against them, so the lexical half of
    #: retrieval was built and then never used. Mapping it here is what lets
    #: ``DocumentChunkRepository.search_chunks_fts`` name the column — and naming it is
    #: the point: ``to_tsvector('spanish', content)`` is an equivalent *expression*, but
    #: Postgres will not match it to an index defined on the generated column, so the
    #: equivalent-looking query does a sequential scan.
    #:
    #: ``Computed`` rather than a plain column so SQLAlchemy leaves it out of every INSERT
    #: and UPDATE; the database is the only writer.
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('spanish'::regconfig, content)", persisted=True),
        nullable=True,
    )

    document: Mapped["Document"] = relationship(back_populates="chunks")
