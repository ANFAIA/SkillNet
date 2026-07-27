"""Shared setup for the integration suites.

One fixture, and it exists for one reason: ``src.deps.db.engine`` is a module-level
:class:`~sqlalchemy.ext.asyncio.AsyncEngine` with a real connection pool, and
pytest-asyncio (1.4, ``asyncio_mode = "auto"``) gives every test function its **own**
event loop. A pooled asyncpg connection belongs to the loop that opened it, so the
second test to run checks out a connection whose loop is already closed and dies with
``InterfaceError: cannot perform operation: another operation is in progress`` — on the
first INSERT, far from the cause, and only when more than one test in the module runs.

Disposing after each test empties the pool inside the loop that owns it, so the next
test opens fresh connections on its own loop. The alternative — a session-scoped loop —
would mean marking every test and fixture with ``loop_scope`` and would let one test's
leaked transaction hang the next.

Autouse and defined here rather than in each module so a new integration file inherits
it. It tears down *last* (autouse fixtures are set up first), i.e. after the per-test
``world`` fixture has deleted its rows.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio

from src.deps.db import engine


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_between_tests() -> AsyncIterator[None]:
    yield
    await engine.dispose()
