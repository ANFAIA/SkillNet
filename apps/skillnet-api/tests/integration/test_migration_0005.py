"""Migration 0005: upgrade from 0004 and downgrade back, with v1 data present.

Requires a live Postgres (``docker compose up db``); excluded from the default
``pytest -m "not integration"`` run. Assertions are exactly the shape §3 promises,
not a byte-identical schema:

* the 13 new tables and the 6 new ``courses`` columns disappear on downgrade;
* the 8 new enum types disappear;
* ``generation_step`` **keeps** ``schema_proposing`` and ``schema_proposed`` —
  orphaned by design, because PostgreSQL cannot drop an enum value;
* no v1 row is altered by either direction;
* swapping positions 1 and 2 in one transaction does not violate the deferrable
  ``uq_course_nodes_position``.

The tests are sync functions on purpose: alembic's env.py calls ``asyncio.run``
itself, which cannot happen inside an already-running loop.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable
from pathlib import Path
from typing import Any, TypeVar

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.config import settings

pytestmark = pytest.mark.integration

API_ROOT = Path(__file__).resolve().parents[2]

NEW_TABLES = (
    "course_nodes",
    "course_node_prerequisites",
    "learner_profiles",
    "learner_node_states",
    "learning_events",
    "node_renders",
    "node_render_views",
    "node_probes",
    "node_attempts",
    "node_feedback",
    "term_explanations",
    "llm_usage_log",
    "audit_log",
)

NEW_COURSES_COLUMNS = (
    "delivery_mode",
    "schema_status",
    "schema_validated_by",
    "schema_validated_at",
    "schema_version",
    "intent_density",
)

NEW_ENUM_TYPES = (
    "course_delivery_mode",
    "course_schema_status",
    "node_criticality",
    "learner_experience",
    "node_state",
    "error_kind",
    "ui_format",
    "node_render_status",
)

ORPHANED_ENUM_VALUES = ("schema_proposing", "schema_proposed")

# Partial unique index on the pre-existing ``generation_jobs``: at most one schema
# job in flight per course (§11.1 propose idempotency).
SCHEMA_IN_FLIGHT_INDEX = "uq_generation_jobs_schema_in_flight"

T = TypeVar("T")


def _alembic_config() -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    return config


def _run(coro: Awaitable[T]) -> T:
    return asyncio.run(coro)  # type: ignore[arg-type]


async def _query(sql: str, **params: Any) -> list[tuple]:
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(sql), params)
            return list(result.fetchall())
    finally:
        await engine.dispose()


async def _exec(statements: list[tuple[str, dict[str, Any]]]) -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.begin() as conn:
            for sql, params in statements:
                await conn.execute(text(sql), params)
    finally:
        await engine.dispose()


def _index_exists(name: str) -> bool:
    rows = _run(
        _query(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'public' AND indexname = :name",
            name=name,
        )
    )
    return bool(rows)


def _existing_tables(names: tuple[str, ...]) -> set[str]:
    rows = _run(
        _query(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = ANY(:names)",
            names=list(names),
        )
    )
    return {row[0] for row in rows}


def _existing_columns(table: str, names: tuple[str, ...]) -> set[str]:
    rows = _run(
        _query(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :table "
            "AND column_name = ANY(:names)",
            table=table,
            names=list(names),
        )
    )
    return {row[0] for row in rows}


def _existing_types(names: tuple[str, ...]) -> set[str]:
    rows = _run(
        _query(
            "SELECT typname FROM pg_type WHERE typname = ANY(:names)",
            names=list(names),
        )
    )
    return {row[0] for row in rows}


def _enum_values(type_name: str) -> list[str]:
    rows = _run(
        _query(
            "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
            "WHERE t.typname = :name ORDER BY e.enumsortorder",
            name=type_name,
        )
    )
    return [row[0] for row in rows]


def _seed_v1_data() -> dict[str, uuid.UUID]:
    ids = {
        "org": uuid.uuid4(),
        "user": uuid.uuid4(),
        "course": uuid.uuid4(),
    }
    suffix = str(ids["org"])[:8]
    _run(
        _exec(
            [
                (
                    "INSERT INTO organizations (id, name, slug) "
                    "VALUES (:id, :name, :slug)",
                    {
                        "id": ids["org"],
                        "name": f"Mig test {suffix}",
                        "slug": f"mig-test-{suffix}",
                    },
                ),
                (
                    "INSERT INTO users (id, org_id, email, hashed_password, full_name) "
                    "VALUES (:id, :org_id, :email, 'x', 'Mig Test User')",
                    {
                        "id": ids["user"],
                        "org_id": ids["org"],
                        "email": f"mig-{suffix}@example.test",
                    },
                ),
                (
                    "INSERT INTO courses (id, org_id, created_by, title, description) "
                    "VALUES (:id, :org_id, :created_by, :title, 'v1 course')",
                    {
                        "id": ids["course"],
                        "org_id": ids["org"],
                        "created_by": ids["user"],
                        "title": f"Mig course {suffix}",
                    },
                ),
            ]
        )
    )
    return ids


def _course_v1_snapshot(course_id: uuid.UUID) -> tuple:
    rows = _run(
        _query(
            "SELECT title, description, outcome, status, org_id, created_by, created_at "
            "FROM courses WHERE id = :id",
            id=course_id,
        )
    )
    assert len(rows) == 1
    return rows[0]


def _cleanup(ids: dict[str, uuid.UUID]) -> None:
    _run(
        _exec(
            [
                ("DELETE FROM courses WHERE id = :id", {"id": ids["course"]}),
                ("DELETE FROM users WHERE id = :id", {"id": ids["user"]}),
                ("DELETE FROM organizations WHERE id = :id", {"id": ids["org"]}),
            ]
        )
    )


def test_upgrade_then_downgrade_leaves_only_the_orphaned_enum_values():
    config = _alembic_config()
    command.upgrade(config, "0004")

    ids = _seed_v1_data()
    try:
        before = _course_v1_snapshot(ids["course"])

        # ── upgrade ─────────────────────────────────────────────
        command.upgrade(config, "0005")

        assert _existing_tables(NEW_TABLES) == set(NEW_TABLES)
        assert _existing_columns("courses", NEW_COURSES_COLUMNS) == set(
            NEW_COURSES_COLUMNS
        )
        assert _existing_types(NEW_ENUM_TYPES) == set(NEW_ENUM_TYPES)
        # The concurrency half of the propose idempotency guard (§11.1). It sits on a
        # pre-existing table, so unlike everything above it is not dropped by a
        # ``DROP TABLE`` and needs its own line in ``downgrade()``.
        assert _index_exists(SCHEMA_IN_FLIGHT_INDEX)

        step_values = _enum_values("generation_step")
        for value in ORPHANED_ENUM_VALUES:
            assert value in step_values
        # Positions asserted by the migration's BEFORE/AFTER clauses.
        assert step_values.index("schema_proposing") < step_values.index("extracting")
        assert step_values.index("schema_proposed") > step_values.index("reviewing")

        # The v1 row is untouched, and the new columns took their defaults.
        after_upgrade = _run(
            _query(
                "SELECT title, description, outcome, status, org_id, created_by, "
                "created_at, delivery_mode, schema_status, schema_version, "
                "intent_density, schema_validated_by, schema_validated_at "
                "FROM courses WHERE id = :id",
                id=ids["course"],
            )
        )[0]
        assert tuple(after_upgrade[:7]) == tuple(before)
        assert after_upgrade[7] == "static"
        assert after_upgrade[8] == "draft"
        assert after_upgrade[9] == 1
        assert after_upgrade[10] == 3
        assert after_upgrade[11] is None
        assert after_upgrade[12] is None

        # ── downgrade ───────────────────────────────────────────
        command.downgrade(config, "0004")

        assert _existing_tables(NEW_TABLES) == set()
        assert _existing_columns("courses", NEW_COURSES_COLUMNS) == set()
        assert _existing_types(NEW_ENUM_TYPES) == set()
        assert not _index_exists(SCHEMA_IN_FLIGHT_INDEX)

        # Orphaned by design: PostgreSQL cannot remove an enum value, and rewriting
        # generation_jobs.status to recreate the type is not worth it.
        step_values_after = _enum_values("generation_step")
        for value in ORPHANED_ENUM_VALUES:
            assert value in step_values_after

        assert _course_v1_snapshot(ids["course"]) == before
    finally:
        _cleanup(ids)
        command.upgrade(config, "head")


def test_deferred_unique_allows_swapping_two_positions_in_one_transaction():
    config = _alembic_config()
    command.upgrade(config, "head")

    ids = _seed_v1_data()
    node_a, node_b = uuid.uuid4(), uuid.uuid4()
    try:
        _run(
            _exec(
                [
                    (
                        "INSERT INTO course_nodes "
                        "(id, org_id, course_id, title, summary, position) "
                        "VALUES (:id, :org_id, :course_id, 'A', 'summary A', 1)",
                        {
                            "id": node_a,
                            "org_id": ids["org"],
                            "course_id": ids["course"],
                        },
                    ),
                    (
                        "INSERT INTO course_nodes "
                        "(id, org_id, course_id, title, summary, position) "
                        "VALUES (:id, :org_id, :course_id, 'B', 'summary B', 2)",
                        {
                            "id": node_b,
                            "org_id": ids["org"],
                            "course_id": ids["course"],
                        },
                    ),
                ]
            )
        )

        # Exactly what PUT /courses/{id}/schema does: defer, then reorder.
        _run(
            _exec(
                [
                    ("SET CONSTRAINTS uq_course_nodes_position DEFERRED", {}),
                    (
                        "UPDATE course_nodes SET position = 2 WHERE id = :id",
                        {"id": node_a},
                    ),
                    (
                        "UPDATE course_nodes SET position = 1 WHERE id = :id",
                        {"id": node_b},
                    ),
                ]
            )
        )

        rows = _run(
            _query(
                "SELECT id, position FROM course_nodes WHERE course_id = :course_id "
                "ORDER BY position",
                course_id=ids["course"],
            )
        )
        assert [(row[0], row[1]) for row in rows] == [(node_b, 1), (node_a, 2)]
    finally:
        _run(
            _exec(
                [
                    (
                        "DELETE FROM course_nodes WHERE course_id = :course_id",
                        {"course_id": ids["course"]},
                    )
                ]
            )
        )
        _cleanup(ids)
