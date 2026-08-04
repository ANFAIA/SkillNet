"""That the configured dimension and the database's match, said out loud at startup.

## Why this exists

A dimension mismatch is not noticeable. `EMBEDDING_DIMENSIONS` decides the size of the
vector asked of the provider; `document_chunks.embedding` has been `vector(768)` since
migration 0008. When they disagree, Postgres rejects the insert — but the rejection lands
inside the `except Exception` of `src/services/ingestion.py`, which logs it as "embedding
unavailable", stores `full_text` and marks the document **`READY`**. The admin sees a
document that looks fine and cannot be retrieved by RAG, and the tutor answers from the
lower rungs of the ladder with nothing anywhere saying why.

It is the most expensive failure there is: silent, late, and looking entirely correct. So
it is checked at startup, where there is a log someone reads, and exposed on `/health`,
which is what a probe looks at.

## Why it does not abort startup

Raising and leaving the container dead was considered. No: SkillNet without embeddings
still serves authentication, v1 courses, lessons, exercises and progress, and the chat
still answers from the lexical rung or from the whole document. Throwing all of that away
over one degraded function would be a worse failure than the one being avoided. It
shouts; it does not die.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.logging import get_logger
from src.repositories.document_chunk_repo import DocumentChunkRepository

logger = get_logger(__name__)

#: Models whose native dimension can be requested to order, so a mismatch is fixed without
#: migrating. Same rule as `EmbeddingService._accepts_dimensions`.
_TRUNCATABLE = "text-embedding-3"


@dataclass(frozen=True)
class EmbeddingCheck:
    """The result of comparing the configuration against the schema."""

    configured: int
    column: int | None

    @property
    def status(self) -> str:
        if self.column is None:
            return "unconstrained"
        return "ok" if self.column == self.configured else "mismatch"

    @property
    def detail(self) -> str | None:
        """What to do, not just what happened. ``None`` when there is nothing to do."""
        if self.status == "ok":
            return None
        if self.status == "unconstrained":
            return (
                "The document_chunks.embedding column is `vector` with no dimension, so "
                "the database does not validate the size. It works, but a model change "
                "would go unnoticed. vector(768) is expected since migration 0008."
            )
        fix = (
            f"set EMBEDDING_DIMENSIONS={self.column} in the .env"
            if _TRUNCATABLE in settings.EMBEDDING_MODEL
            else (
                f"set EMBEDDING_DIMENSIONS={self.column} and a model that returns "
                f"{self.column} dimensions, or migrate the column and re-ingest the documents"
            )
        )
        return (
            f"EMBEDDING_DIMENSIONS={self.configured} but document_chunks.embedding is "
            f"vector({self.column}). Every chunk insert is going to fail and the document "
            f"will be indexed as full text only, with no visible error. "
            f"Fix: {fix}."
        )


async def check_embedding_dimensions(session: AsyncSession) -> EmbeddingCheck:
    """Compare `EMBEDDING_DIMENSIONS` against the column, and log the mismatch."""
    column = await DocumentChunkRepository(session).column_dimensions()
    check = EmbeddingCheck(configured=settings.EMBEDDING_DIMENSIONS, column=column)

    if check.status == "mismatch":
        logger.error("Inconsistent embedding configuration. %s", check.detail)
    elif check.status == "unconstrained":
        logger.warning("Unvalidated embedding configuration. %s", check.detail)
    else:
        logger.info(
            "Embeddings: %s at %d dimensions, matches the column.",
            settings.EMBEDDING_MODEL,
            check.configured,
        )
    return check
