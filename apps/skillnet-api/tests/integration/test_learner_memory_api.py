"""Integration: the ``/users/me/memory`` self-service endpoints and the DB-backed service.

Needs a live Postgres (``-m integration``). Seeds a minimal org + employee, exercises the
three GDPR verbs end-to-end through the app, and checks the one thing pure unit tests cannot:
that :meth:`LearnerMemoryService.note` reads and writes the ``learner_profiles.memory_md``
column and survives the round-trip a learner's edit puts it through.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from src.deps.auth import current_user
from src.deps.db import async_session_factory
from src.main import create_app
from src.models import Organization, User, UserRole
from src.repositories.learner_profile_repo import LearnerProfileRepository
from src.services.learner_memory import LearnerMemoryService

pytestmark = pytest.mark.integration

PREFIX = "/api/v1"


class World:
    def __init__(self, *, org: Organization, employee: User, admin: User) -> None:
        self.org = org
        self.employee = employee
        self.admin = admin


async def _seed() -> World:
    suffix = uuid.uuid4().hex[:8]
    async with async_session_factory() as db:
        org = Organization(name=f"Mem {suffix}", slug=f"mem-{suffix}", settings={})
        db.add(org)
        await db.flush()
        employee = User(
            org_id=org.id,
            email=f"empleado-{suffix}@mem.example",
            hashed_password="x",
            full_name="Empleada memoria",
            role=UserRole.EMPLOYEE,
            is_active=True,
        )
        admin = User(
            org_id=org.id,
            email=f"admin-{suffix}@mem.example",
            hashed_password="x",
            full_name="Admin memoria",
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add_all([employee, admin])
        await db.commit()
        for instance in (org, employee, admin):
            await db.refresh(instance)
    return World(org=org, employee=employee, admin=admin)


async def _cleanup(world: World) -> None:
    async with async_session_factory() as db:
        await db.execute(
            text("DELETE FROM learner_profiles WHERE org_id = :org"),
            {"org": world.org.id},
        )
        await db.execute(
            text("DELETE FROM users WHERE org_id = :org"), {"org": world.org.id}
        )
        await db.execute(
            text("DELETE FROM organizations WHERE id = :org"), {"org": world.org.id}
        )
        await db.commit()


@pytest_asyncio.fixture
async def world() -> AsyncIterator[World]:
    seeded = await _seed()
    try:
        yield seeded
    finally:
        await _cleanup(seeded)


class Actor:
    def __init__(self, user: User) -> None:
        self.user = user
        self.app = create_app()
        self.app.dependency_overrides[current_user] = lambda: user
        self.client = AsyncClient(
            transport=ASGITransport(app=self.app), base_url="http://mem.test"
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def request(self, method: str, path: str, **kw: Any) -> Any:
        return await self.client.request(method, f"{PREFIX}{path}", **kw)


@pytest_asyncio.fixture
async def employee(world: World) -> AsyncIterator[Actor]:
    actor = Actor(world.employee)
    try:
        yield actor
    finally:
        await actor.close()


@pytest_asyncio.fixture
async def admin(world: World) -> AsyncIterator[Actor]:
    actor = Actor(world.admin)
    try:
        yield actor
    finally:
        await actor.close()


async def test_get_returns_empty_skeleton_without_a_profile(employee: Actor) -> None:
    resp = await employee.request("GET", "/users/me/memory")
    assert resp.status_code == 200
    body = resp.json()
    assert "## Perfil declarado" in body["memory_md"]
    assert body["memory_updated_at"] is None


async def test_note_then_get_reads_it_back(world: World, employee: Actor) -> None:
    async with async_session_factory() as db:
        service = LearnerMemoryService(LearnerProfileRepository(db))
        await service.note(
            user_id=world.employee.id,
            org_id=world.org.id,
            section="Preferencias de contenido",
            text="Pidió enfoque: 'más ejemplos de caja' en podcast",
            source="media",
        )
        await db.commit()

    resp = await employee.request("GET", "/users/me/memory")
    assert resp.status_code == 200
    assert "más ejemplos de caja" in resp.json()["memory_md"]


async def test_put_requires_a_profile_then_rectifies(
    world: World, employee: Actor
) -> None:
    edited = (
        "## Preferencias de contenido\n- Prefiere vídeo corto\n\n## Notas del tutor\n"
    )
    # No profile row yet → 404 (nothing to rectify).
    missing = await employee.request("PUT", "/users/me/memory", json={"memory_md": edited})
    assert missing.status_code == 404

    # Create the row, then the PUT rectifies and normalizes back to the five sections.
    async with async_session_factory() as db:
        await LearnerProfileRepository(db).get_or_create(
            user_id=world.employee.id, org_id=world.org.id
        )
        await db.commit()

    resp = await employee.request("PUT", "/users/me/memory", json={"memory_md": edited})
    assert resp.status_code == 200
    md = resp.json()["memory_md"]
    assert "- Prefiere vídeo corto" in md
    assert md.count("## Perfil declarado") == 1  # normalized skeleton present
    assert resp.json()["memory_updated_at"] is not None


async def test_delete_erases_the_notebook(world: World, employee: Actor) -> None:
    async with async_session_factory() as db:
        service = LearnerMemoryService(LearnerProfileRepository(db))
        await service.note(
            user_id=world.employee.id,
            org_id=world.org.id,
            section="Notas del tutor",
            text="algo que recordar",
            source="tutor",
        )
        await db.commit()

    erased = await employee.request("DELETE", "/users/me/memory")
    assert erased.status_code == 204
    # Idempotent: a second erase is still 204.
    again = await employee.request("DELETE", "/users/me/memory")
    assert again.status_code == 204

    resp = await employee.request("GET", "/users/me/memory")
    assert "algo que recordar" not in resp.json()["memory_md"]


async def test_admin_has_no_access(admin: Actor) -> None:
    # Employee-only scope: the admin is forbidden from the learner's private notebook.
    resp = await admin.request("GET", "/users/me/memory")
    assert resp.status_code == 403
