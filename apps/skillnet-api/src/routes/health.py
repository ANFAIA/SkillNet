"""Public health check."""

from fastapi import APIRouter
from sqlalchemy import text

from src.config import settings
from src.core.logging import get_logger
from src.deps.db import DBSession
from src.services.embedding_check import check_embedding_dimensions

logger = get_logger(__name__)

router = APIRouter()


@router.get("/health", tags=["Health"])
async def health(db: DBSession) -> dict:
    database = "connected"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - report as degraded, never crash
        logger.warning("Health check DB probe failed: %s", exc)
        database = "error"

    # Los embeddings, porque un desajuste de dimension no se ve de ninguna otra forma:
    # la insercion falla dentro del `except` de la ingesta, el documento queda `READY`
    # con solo `full_text`, y el tutor responde por los peldanos de abajo sin decir por
    # que. Aqui lo ve una sonda; el arranque ademas lo escribe en el log.
    embeddings: dict[str, object] = {"status": "unknown", "model": settings.EMBEDDING_MODEL}
    if database == "connected":
        try:
            check = await check_embedding_dimensions(db)
            embeddings = {
                "status": check.status,
                "model": settings.EMBEDDING_MODEL,
                "configured_dimensions": check.configured,
                "column_dimensions": check.column,
            }
            if check.detail:
                embeddings["detail"] = check.detail
        except Exception as exc:  # noqa: BLE001 - degradar, nunca tumbar el health
            logger.warning("Health check embedding probe failed: %s", exc)
            embeddings["status"] = "error"

    # The only place the dynamic-courses flag is exposed. NOT /auth/me: that route
    # returns the ORM user through UserRead, which has no `features` column, so the
    # field would either raise or serialize a stale default forever.
    return {
        "status": "ok",
        "version": "0.1.0",
        "database": database,
        "embeddings": embeddings,
        "features": {"dynamic_courses": settings.DYNAMIC_COURSES_MODE},
    }
