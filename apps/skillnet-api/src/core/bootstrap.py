"""Idempotent startup routines: migrations, default org, admin, and API key bootstrap."""

import hashlib
import threading
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.logging import get_logger
from src.models import ApiKey, Organization, User, UserRole

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


async def maybe_create_a2a_api_key(
    session: AsyncSession, org: Organization
) -> None:
    """Create an internal A2A API key from the env var if not already present."""
    raw_key = settings.A2A_INTERNAL_API_KEY
    if not raw_key:
        return

    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    existing = await session.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash)
    )
    if existing.scalar_one_or_none() is not None:
        return

    # We need a user to attribute the key to. Use the first admin.
    admin_result = await session.execute(
        select(User).where(User.org_id == org.id, User.role == UserRole.ADMIN).limit(1)
    )
    admin = admin_result.scalar_one_or_none()
    if admin is None:
        logger.warning("Cannot create A2A API key: no admin user found")
        return

    api_key = ApiKey(
        org_id=org.id,
        created_by=admin.id,
        name="A2A Internal",
        key_hash=key_hash,
        scopes=["skills:read", "skills:write", "users:read"],
        is_active=True,
    )
    session.add(api_key)
    await session.commit()
    logger.info("Created A2A internal API key for org %s", org.name)


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
