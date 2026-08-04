"""Alembic async environment."""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from src.config import settings
from src.models import Base

config = context.config

if config.config_file_name is not None:
    # Only when Alembic owns the process. Applying `alembic.ini`'s logging inside the API
    # silenced the application, and it did so in two ways at once:
    #
    #  1. `logging.config.fileConfig` defaults `disable_existing_loggers` to **True**, so
    #     it switched off every logger the app had already created.
    #  2. `alembic.ini` sets `[logger_root] level = WARNING`, which it applies to the root
    #     logger — so even a re-created logger emitted nothing below WARNING.
    #
    # Migrations run from the app's own lifespan (`src/main.py` calls `configure_logging()`
    # at import and `run_migrations()` a few lines into the lifespan), so everything logged
    # *after* migrating vanished: the org/admin bootstrap, the embedding-dimension check
    # that exists precisely to make a silent misconfiguration loud, and LLM errors.
    #
    # The symptom was misleading in both directions. Alembic's own lines kept appearing —
    # its loggers are created after this call and `alembic.ini` sets them to INFO — so the
    # log looked alive, and it read like output buffering. It was not.
    #
    # `context.is_offline_mode()` is not the test that matters here; what matters is
    # whether this process is `alembic` on a terminal or the API server. The API sets
    # `SKILLNET_APP_LOGGING`, and only it does.
    if not os.getenv("SKILLNET_APP_LOGGING"):
        fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a DB connection (emits SQL)."""
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(settings.DATABASE_URL)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
