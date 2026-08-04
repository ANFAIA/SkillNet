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

    # Embeddings, because a dimension mismatch is invisible any other way: the insert
    # fails inside the ingestion `except`, the document ends up `READY` with only
    # `full_text`, and the tutor answers from the lower rungs without saying why. Here a
    # probe can see it; startup also writes it to the log.
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
        except Exception as exc:  # noqa: BLE001 - degrade, never take health down
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
