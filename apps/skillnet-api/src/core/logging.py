"""Stdlib logging configuration."""

import logging
import os

_CONFIGURED = False

#: Tells `alembic/env.py` that this process is the API server, not the `alembic` CLI, so it
#: must leave logging alone. See the long comment there: applying `alembic.ini`'s
#: `[logger_root] level = WARNING` inside the app silenced everything the lifespan logged
#: after running migrations, including the check that exists to make a bad embedding
#: dimension loud.
_APP_LOGGING_ENV = "SKILLNET_APP_LOGGING"


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging once. Idempotent."""
    global _CONFIGURED
    os.environ[_APP_LOGGING_ENV] = "1"
    numeric_level = logging.getLevelName(level.upper())
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        force=not _CONFIGURED,
    )
    logging.getLogger().setLevel(numeric_level)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
