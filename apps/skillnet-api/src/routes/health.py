"""Public health check."""

from fastapi import APIRouter
from sqlalchemy import text

from src.config import settings
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
    # The only place the dynamic-courses flag is exposed. NOT /auth/me: that route
    # returns the ORM user through UserRead, which has no `features` column, so the
    # field would either raise or serialize a stale default forever.
    return {
        "status": "ok",
        "version": "0.1.0",
        "database": database,
        "features": {"dynamic_courses": settings.DYNAMIC_COURSES_MODE},
    }
