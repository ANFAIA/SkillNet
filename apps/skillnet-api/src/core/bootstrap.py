"""Idempotent startup routines: migrations, default org, and admin bootstrap."""

import threading
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.logging import get_logger
from src.models import Organization, User, UserRole

logger = get_logger(__name__)


async def ensure_organization(session: AsyncSession) -> Organization:
    """Return the single organization row, creating it if none exists."""
    result = await session.execute(select(Organization).limit(1))
    org = result.scalar_one_or_none()
    if org is not None:
        return org

    org = Organization(name=settings.ORG_NAME or "SkillNet", slug="default")
    session.add(org)
    await session.commit()
    await session.refresh(org)
    logger.info("Created default organization: %s", org.name)
    return org


async def maybe_create_admin(session: AsyncSession) -> None:
    """Create an admin user from ADMIN_EMAIL/ADMIN_PASSWORD if not present."""
    if not settings.ADMIN_EMAIL or not settings.ADMIN_PASSWORD:
        return

    existing = await session.execute(
        select(User).where(User.email == settings.ADMIN_EMAIL)
    )
    if existing.scalar_one_or_none() is not None:
        return

    from fastapi_users.password import PasswordHelper

    org = await ensure_organization(session)
    hashed_password = PasswordHelper().hash(settings.ADMIN_PASSWORD)
    full_name = settings.ADMIN_EMAIL.split("@", 1)[0]

    admin = User(
        email=settings.ADMIN_EMAIL,
        hashed_password=hashed_password,
        org_id=org.id,
        full_name=full_name,
        role=UserRole.ADMIN,
        is_active=True,
        is_superuser=True,
        is_verified=True,
    )
    session.add(admin)
    await session.commit()
    logger.info("Created bootstrap admin user: %s", settings.ADMIN_EMAIL)


def run_migrations() -> None:
    """Run alembic ``upgrade head``. Safe to call at startup (logs on failure)."""
    ini_path = Path(__file__).resolve().parents[2] / "alembic.ini"

    def _upgrade() -> None:
        try:
            from alembic import command
            from alembic.config import Config

            config = Config(str(ini_path))
            command.upgrade(config, "head")
            logger.info("Alembic migrations applied (upgrade head).")
        except Exception as exc:  # noqa: BLE001 - migrations must not crash startup
            logger.error("Alembic migration failed: %s", exc)

    # Alembic's async env.py calls asyncio.run(), which cannot run inside the
    # already-running startup event loop. Run it in a dedicated thread instead.
    thread = threading.Thread(target=_upgrade, name="alembic-upgrade")
    thread.start()
    thread.join()
