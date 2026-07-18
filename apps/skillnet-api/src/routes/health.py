"""Public health check."""

from fastapi import APIRouter
from sqlalchemy import text

from src.core.logging import get_logger
from src.deps.db import DBSession

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
    return {"status": "ok", "version": "0.1.0", "database": database}
