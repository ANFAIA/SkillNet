"""Que la dimension configurada y la de la base coincidan, dicho al arrancar.

## Por que existe

Un desajuste de dimension no se nota. `EMBEDDING_DIMENSIONS` decide el tamano del vector
que se le pide al proveedor; `document_chunks.embedding` es `vector(768)` desde la
migracion 0008. Si no coinciden, Postgres rechaza la insercion — pero el rechazo cae
dentro del `except Exception` de `src/services/ingestion.py`, que lo registra como
"embedding unavailable", guarda `full_text` y marca el documento **`READY`**. El admin ve
un documento correcto que no se puede recuperar por RAG, y el tutor responde por los
peldanos de abajo de la escalera sin que nada indique por que.

Es el fallo mas caro posible: silencioso, tardio, y con toda la pinta de estar bien. Asi
que se comprueba al arrancar, donde hay un log que alguien lee, y se expone en `/health`,
que es lo que mira una sonda.

## Por que no aborta el arranque

Se penso en lanzar y dejar el contenedor muerto. No: SkillNet sin embeddings sigue
sirviendo autenticacion, cursos v1, lecciones, ejercicios y progreso, y el chat sigue
respondiendo por el peldano lexico o por documento completo. Tirar todo eso por una
funcion degradada seria un fallo peor que el que se quiere evitar. Se grita, no se muere.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.logging import get_logger
from src.repositories.document_chunk_repo import DocumentChunkRepository

logger = get_logger(__name__)

#: Modelos cuya dimension nativa se puede pedir a medida, asi que un desajuste se arregla
#: sin migrar. Mismo criterio que `EmbeddingService._accepts_dimensions`.
_TRUNCATABLE = "text-embedding-3"


@dataclass(frozen=True)
class EmbeddingCheck:
    """Resultado de comparar la configuracion con el esquema."""

    configured: int
    column: int | None

    @property
    def status(self) -> str:
        if self.column is None:
            return "unconstrained"
        return "ok" if self.column == self.configured else "mismatch"

    @property
    def detail(self) -> str | None:
        """Que hacer, no solo que pasa. ``None`` cuando no hay nada que hacer."""
        if self.status == "ok":
            return None
        if self.status == "unconstrained":
            return (
                "La columna document_chunks.embedding es `vector` sin dimension, asi que "
                "la base no valida el tamano. Funciona, pero un cambio de modelo pasaria "
                "inadvertido. Se espera vector(768) desde la migracion 0008."
            )
        arreglo = (
            f"pon EMBEDDING_DIMENSIONS={self.column} en el .env"
            if _TRUNCATABLE in settings.EMBEDDING_MODEL
            else (
                f"pon EMBEDDING_DIMENSIONS={self.column} y un modelo que devuelva "
                f"{self.column} dimensiones, o migra la columna y reingiere los documentos"
            )
        )
        return (
            f"EMBEDDING_DIMENSIONS={self.configured} pero document_chunks.embedding es "
            f"vector({self.column}). Cada insercion de chunk va a fallar y el documento "
            f"se quedara indexado solo como texto completo, sin error visible. "
            f"Arreglo: {arreglo}."
        )


async def check_embedding_dimensions(session: AsyncSession) -> EmbeddingCheck:
    """Comparar `EMBEDDING_DIMENSIONS` con la columna, y registrar el desajuste."""
    column = await DocumentChunkRepository(session).column_dimensions()
    check = EmbeddingCheck(configured=settings.EMBEDDING_DIMENSIONS, column=column)

    if check.status == "mismatch":
        logger.error("Configuracion de embeddings incoherente. %s", check.detail)
    elif check.status == "unconstrained":
        logger.warning("Configuracion de embeddings sin validar. %s", check.detail)
    else:
        logger.info(
            "Embeddings: %s a %d dimensiones, coincide con la columna.",
            settings.EMBEDDING_MODEL,
            check.configured,
        )
    return check
