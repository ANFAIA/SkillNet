"""With ``DYNAMIC_COURSES_MODE=off``, v1 behaves exactly as it did. This is the test
that justifies the flag.

Everything the v2 work added is either a new file or an additive change behind
``resolve_delivery`` / ``require_dynamic_courses``. That is a claim, and a claim about a
production system that people are already using needs evidence, not a code review. So
this file runs the **whole** v1 path against a real Postgres with the flag off:

1. Every v2 route of §11 answers ``404`` — indistinguishable from a route that does not
   exist, which is what §10.1 promises. Enumerated by hand, one line per path, because a
   loop over the OpenAPI schema would silently stop covering a path that got removed
   from the app.
2. ``shadow`` opens the **admin** surface and leaves the **employee** surface at ``404``
   — the middle row of §10.1's table, which is the mode the internal demo runs in.
3. ``POST /courses/{id}/generate`` still drives the v1 LangGraph pipeline to
   ``published``: themes -> structure -> modules -> review -> publish, with real
   modules, lessons and exercises in the database. Recorded LLM responses, keyed on the
   prompts the v1 builders produce (§12.1), so this exercises the pipeline and not a
   stub.
4. The v1 learner journey closes a course by the v1 rule (every lesson visited, every
   exercise passed) and grants ``user_skills`` at ``medium`` — **not** at the
   ``mastery -> skill_level`` translation B11 added, which is dynamic-branch only.
5. The additive columns of migration 0005 take their defaults on a course v1 created,
   and a course somebody flips to ``dynamic`` while the flag is off is still served by
   v1. That last one is the whole point of ``resolve_delivery`` being one function.

Run it with::

    docker compose up -d db
    uv run pytest -m integration tests/integration/test_v1_regression.py -v
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Awaitable
from pathlib import Path
from typing import Any, TypeVar

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from src.agents.content.helpers import estimate_pages
from src.config import settings
from src.deps.auth import current_user
from src.deps.db import async_session_factory, engine
from src.llm.fixtures import write_fixture
from src.llm.prompts import (
    MODULE_GENERATOR_SYSTEM,
    QUALITY_REVIEWER_SYSTEM,
    STRUCTURE_DESIGNER_SYSTEM,
    THEME_EXTRACTOR_SYSTEM,
    build_extraction_prompt,
    build_module_prompt,
    build_review_prompt,
    build_structure_prompt,
)
from src.main import create_app
from src.models import (
    Course,
    CourseDeliveryMode,
    CourseSchemaStatus,
    ContentStatus,
    Document,
    DocumentStatus,
    Enrollment,
    EnrollmentStatus,
    Exercise,
    Lesson,
    Module,
    Organization,
    User,
    UserRole,
)
from src.models.user_skill import SkillLevel, UserSkill
from src.services.course_delivery import resolve_delivery

pytestmark = pytest.mark.integration

API_ROOT = Path(__file__).resolve().parents[2]
PREFIX = "/api/v1"
T = TypeVar("T")

DOC_TITLE = "Manual de caja"
DOC_FULL_TEXT = (
    "Manual de caja\n\n"
    "Al abrir el turno se cuenta el efectivo del cajon y se anota en la hoja de "
    "apertura. Al cerrar se repite el recuento y se cuadra con el ticket Z.\n\n"
    "Si el descuadre supera cinco euros se avisa al encargado antes de cerrar."
)
COURSE_TITLE = "Apertura y cierre de caja"

# --- the four v1 pipeline recordings ---------------------------------------------
#
# Written as Python and dumped with the same `json.dumps` the graph parses back, so the
# structures below are literally what the pipeline will see.
THEMES_PAYLOAD: dict[str, Any] = {
    "themes": [
        {"name": "Recuento de caja", "description": "Contar el efectivo al abrir y cerrar."},
    ]
}
OUTLINE_PAYLOAD: dict[str, Any] = {
    "title": COURSE_TITLE,
    "description": "Como abrir y cerrar la caja sin descuadres.",
    "outcome": "Cuadrar la caja al cerrar el turno",
    "modules": [
        {
            "position": 1,
            "title": "Recuento de caja",
            "summary": "Contar el efectivo y cuadrar con el ticket Z.",
        }
    ],
}
MODULE_PAYLOAD: dict[str, Any] = {
    "lessons": [
        {
            "position": 1,
            "title": "Recuento de apertura",
            "content": "Al abrir el turno se cuenta el efectivo y se anota.",
        },
        {
            "position": 2,
            "title": "Recuento de cierre",
            "content": "Al cerrar se repite el recuento y se cuadra con el ticket Z.",
        },
    ],
    "exercises": [
        {
            "position": 0,
            "type": "test",
            "content": {
                "question": "El descuadre es de seis euros. Que haces?",
                "options": [
                    "Cerrar y anotarlo en la hoja",
                    "Avisar al encargado antes de cerrar",
                    "Repetir el recuento y cerrar igual",
                    "Dejarlo para el turno siguiente",
                ],
                "correct": 1,
                "explanation": "Por encima de cinco euros se avisa al encargado.",
            },
        }
    ],
}
REVIEW_PAYLOAD: dict[str, Any] = {
    "passed": True,
    "overall_score": 0.92,
    "issues": [],
}

EXERCISE_CORRECT = 1
EXERCISE_WRONG = 0
JOB_POLL_ATTEMPTS = 300
JOB_POLL_SECONDS = 0.25


# --------------------------------------------------------------------------------- #
# Infrastructure
# --------------------------------------------------------------------------------- #
def _run(coro: Awaitable[T]) -> T:
    return asyncio.run(coro)  # type: ignore[arg-type]


async def _probe_database() -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


@pytest.fixture(scope="module", autouse=True)
def _migrated_database() -> None:
    try:
        _run(_probe_database())
    except Exception as exc:  # noqa: BLE001 - a missing DB is a skip, not a failure
        pytest.skip(f"No Postgres at DATABASE_URL ({type(exc).__name__}: {exc}).")
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    command.upgrade(config, "head")
    _run(engine.dispose())


@pytest.fixture(autouse=True)
def _flag_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The default production configuration: the flag off, the LLM on disk."""
    monkeypatch.setattr(settings, "DYNAMIC_COURSES_MODE", "off")
    monkeypatch.setattr(settings, "LLM_MODEL", "fixture/local")
    monkeypatch.setattr(settings, "EMBEDDING_MODEL", "fixture/local")
    monkeypatch.setattr(settings, "LLM_FIXTURE_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "LLM_FIXTURE_MODE", "replay")
    return tmp_path


class World:
    def __init__(self, *, org: Organization, admin: User, employee: User,
                 document: Document) -> None:
        self.org = org
        self.admin = admin
        self.employee = employee
        self.document = document
        self.course_ids: list[uuid.UUID] = []


async def _seed() -> World:
    suffix = uuid.uuid4().hex[:8]
    async with async_session_factory() as db:
        org = Organization(name=f"V1 {suffix}", slug=f"v1-{suffix}", settings={})
        db.add(org)
        await db.flush()
        admin = User(
            org_id=org.id,
            # `@v1.test` looks harmless but `email-validator` — which `EmailStr` runs on
            # the way *out* of `/auth/me` too, not just on input — rejects `.test` as a
            # special-use reserved TLD (RFC 2606). Seeded rows go in through the ORM,
            # which does not validate, so the bad domain only surfaces as a
            # `ResponseValidationError` when a route serializes the user. `.example` is
            # the reserved-for-documentation domain the validator does accept.
            email=f"admin-{suffix}@v1.example",
            hashed_password="x",
            full_name="Admin v1",
            role=UserRole.ADMIN,
            is_active=True,
        )
        employee = User(
            org_id=org.id,
            email=f"empleado-{suffix}@v1.example",
            hashed_password="x",
            full_name="Empleado v1",
            role=UserRole.EMPLOYEE,
            is_active=True,
        )
        db.add_all([admin, employee])
        await db.flush()
        document = Document(
            org_id=org.id,
            uploaded_by=admin.id,
            title=DOC_TITLE,
            storage_path=f"uploads/{suffix}.md",
            file_type="md",
            size_bytes=len(DOC_FULL_TEXT),
            status=DocumentStatus.READY,
            full_text=DOC_FULL_TEXT,
            page_count=1,
        )
        db.add(document)
        await db.commit()
        # Refresh before the session closes. These instances are handed straight to the
        # app (`dependency_overrides[current_user]`), and `UserRead` reads columns the
        # seed never sets — `accessibility`, `is_superuser`. On a detached object those
        # are expired attributes, and touching one raises `MissingGreenlet` instead of
        # lazily loading. A real request never hits this: it loads its own user.
        for instance in (org, admin, employee, document):
            await db.refresh(instance)
    return World(org=org, admin=admin, employee=employee, document=document)


async def _cleanup(world: World) -> None:
    async with async_session_factory() as db:
        await db.execute(
            text("DELETE FROM exercise_attempts WHERE user_id = ANY(:ids)"),
            {"ids": [world.employee.id, world.admin.id]},
        )
        await db.execute(
            text("DELETE FROM lesson_progress WHERE user_id = ANY(:ids)"),
            {"ids": [world.employee.id, world.admin.id]},
        )
        await db.execute(
            text("DELETE FROM enrollments WHERE user_id = ANY(:ids)"),
            {"ids": [world.employee.id, world.admin.id]},
        )
        await db.execute(
            text("DELETE FROM user_skills WHERE user_id = ANY(:ids)"),
            {"ids": [world.employee.id, world.admin.id]},
        )
        await db.execute(
            text("DELETE FROM chat_messages WHERE session_id IN "
                 "(SELECT id FROM chat_sessions WHERE user_id = ANY(:ids))"),
            {"ids": [world.employee.id, world.admin.id]},
        )
        await db.execute(
            text("DELETE FROM chat_sessions WHERE user_id = ANY(:ids)"),
            {"ids": [world.employee.id, world.admin.id]},
        )
        await db.execute(
            text("DELETE FROM generation_jobs WHERE org_id = :org"), {"org": world.org.id}
        )
        await db.execute(
            text("DELETE FROM course_skills WHERE course_id IN "
                 "(SELECT id FROM courses WHERE org_id = :org)"),
            {"org": world.org.id},
        )
        await db.execute(
            text("DELETE FROM courses WHERE org_id = :org"), {"org": world.org.id}
        )
        await db.execute(
            text("DELETE FROM skills WHERE org_id = :org"), {"org": world.org.id}
        )
        await db.execute(
            text("DELETE FROM documents WHERE org_id = :org"), {"org": world.org.id}
        )
        await db.execute(
            text("DELETE FROM users WHERE org_id = :org"), {"org": world.org.id}
        )
        await db.execute(
            text("DELETE FROM organizations WHERE id = :org"), {"org": world.org.id}
        )
        await db.commit()


@pytest_asyncio.fixture
async def world(_flag_off: Path) -> AsyncIterator[World]:
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
            transport=ASGITransport(app=self.app), base_url="http://v1.test"
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def request(self, method: str, path: str, **kw: Any) -> Any:
        return await self.client.request(method, f"{PREFIX}{path}", **kw)

    async def get(self, path: str, **kw: Any) -> Any:
        return await self.request("GET", path, **kw)

    async def post(self, path: str, **kw: Any) -> Any:
        return await self.request("POST", path, **kw)

    async def put(self, path: str, **kw: Any) -> Any:
        return await self.request("PUT", path, **kw)


@pytest_asyncio.fixture
async def admin(world: World) -> AsyncIterator[Actor]:
    actor = Actor(world.admin)
    try:
        yield actor
    finally:
        await actor.close()


@pytest_asyncio.fixture
async def employee(world: World) -> AsyncIterator[Actor]:
    actor = Actor(world.employee)
    try:
        yield actor
    finally:
        await actor.close()


# --------------------------------------------------------------------------------- #
# The v2 surface, enumerated
#
# Imported from the unit-level twin rather than copied: ``tests/test_flag_surface.py``
# asserts the same §10.1 truth table without a database (so it runs in CI) and owns the
# list, including the drift alarm that cross-checks it against the app's own OpenAPI
# schema. What *this* file adds is the same table with real authentication, real rows and
# the whole v1 flow running beside it.
# --------------------------------------------------------------------------------- #
from tests.test_flag_surface import (  # noqa: E402 - grouped with what it documents
    ADMIN_SURFACE,
    EMPLOYEE_SURFACE,
)


@pytest.mark.asyncio
async def test_with_the_flag_off_every_v2_route_is_a_404(admin: Actor) -> None:
    """``404``, not ``403``: with the flag off the v2 surface must be
    indistinguishable from routes that were never deployed (§10.1)."""
    for method, path, body in ADMIN_SURFACE + EMPLOYEE_SURFACE:
        response = await admin.request(
            method, path, **({"json": body} if body is not None else {})
        )
        assert response.status_code == 404, f"{method} {path} -> {response.status_code}"


@pytest.mark.asyncio
async def test_health_reports_the_flag_and_nothing_else_changed(admin: Actor) -> None:
    for path in ("/health", f"{PREFIX}/health"):
        response = await admin.client.get(path)
        assert response.status_code == 200
        body = response.json()
        # The v1 keys, unchanged.
        assert body["status"] == "ok"
        assert body["version"] == "0.1.0"
        assert body["database"] == "connected"
        # The one addition, and the only place the flag is exposed (§10.1).
        assert body["features"] == {"dynamic_courses": "off"}

    # It is NOT on /auth/me — adding it to `UserRead` would serialize a stale default.
    me = await admin.get("/auth/me")
    assert me.status_code == 200
    assert "features" not in me.json()


@pytest.mark.asyncio
async def test_shadow_opens_the_admin_surface_and_leaves_the_employee_one_shut(
    admin: Actor, employee: Actor, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The middle row of §10.1: the creator can work on schemas with real data while
    no learner can reach anything."""
    monkeypatch.setattr(settings, "DYNAMIC_COURSES_MODE", "shadow")

    # The admin surface exists. A missing course is a 404 too, so use a real one and
    # assert on the *reason* instead: the route ran and answered about the resource.
    created = await admin.post(
        "/courses",
        json={"title": COURSE_TITLE, "source_document_id": str(world.document.id)},
    )
    assert created.status_code == 201, created.text
    course_id = uuid.UUID(created.json()["id"])
    world.course_ids.append(course_id)

    schema = await admin.get(f"/courses/{course_id}/schema")
    assert schema.status_code == 200, schema.text
    assert schema.json()["schema_status"] == "draft"
    assert schema.json()["nodes"] == []

    # The employee surface does not.
    for method, path, body in EMPLOYEE_SURFACE:
        response = await employee.request(
            method, path, **({"json": body} if body is not None else {})
        )
        assert response.status_code == 404, f"{method} {path} -> {response.status_code}"

    # And an employee still cannot reach the admin surface: the flag guard is not a
    # substitute for the role guard.
    forbidden = await employee.get(f"/courses/{course_id}/schema")
    assert forbidden.status_code == 403, forbidden.text


# --------------------------------------------------------------------------------- #
# The v1 generation pipeline
# --------------------------------------------------------------------------------- #
def _register_v1_fixtures(directory: Path, *, document: Document) -> None:
    """The four recordings of the v1 happy path, keyed on the v1 builders' prompts."""
    source_metadata = {
        "total_pages": estimate_pages(document),
        "doc_count": 1,
        "doc_titles": [DOC_TITLE],
    }
    write_fixture(
        system_prompt=THEME_EXTRACTOR_SYSTEM,
        user_prompt=build_extraction_prompt(DOC_FULL_TEXT),
        response=json.dumps(THEMES_PAYLOAD, ensure_ascii=False),
        relative_path="v1/themes.json",
        use_case="generation",
        directory=directory,
    )
    write_fixture(
        system_prompt=STRUCTURE_DESIGNER_SYSTEM,
        user_prompt=build_structure_prompt(THEMES_PAYLOAD["themes"], source_metadata),
        response=json.dumps(OUTLINE_PAYLOAD, ensure_ascii=False),
        relative_path="v1/outline.json",
        use_case="generation",
        directory=directory,
    )
    write_fixture(
        system_prompt=MODULE_GENERATOR_SYSTEM,
        user_prompt=build_module_prompt(OUTLINE_PAYLOAD["modules"][0], DOC_FULL_TEXT),
        response=json.dumps(MODULE_PAYLOAD, ensure_ascii=False),
        relative_path="v1/module.json",
        use_case="generation",
        directory=directory,
    )
    # `review_quality` reviews exactly the structure `generate_modules` returns, dumped
    # with the same call. Rebuilt here rather than approximated, because the prompt is
    # the fixture key.
    generated = json.dumps(
        [
            {
                "module_spec": OUTLINE_PAYLOAD["modules"][0],
                "lessons": MODULE_PAYLOAD["lessons"],
                "exercises": MODULE_PAYLOAD["exercises"],
            }
        ],
        ensure_ascii=False,
        default=str,
    )
    write_fixture(
        system_prompt=QUALITY_REVIEWER_SYSTEM,
        user_prompt=build_review_prompt(DOC_FULL_TEXT, generated),
        response=json.dumps(REVIEW_PAYLOAD, ensure_ascii=False),
        relative_path="v1/review.json",
        use_case="generation",
        directory=directory,
    )


async def _generate_v1_course(admin: Actor, world: World, fixture_dir: Path) -> uuid.UUID:
    _register_v1_fixtures(fixture_dir, document=world.document)
    created = await admin.post(
        "/courses",
        json={"title": COURSE_TITLE, "source_document_id": str(world.document.id)},
    )
    assert created.status_code == 201, created.text
    course_id = uuid.UUID(created.json()["id"])
    world.course_ids.append(course_id)

    started = await admin.post(f"/courses/{course_id}/generate", json={})
    assert started.status_code == 202, started.text
    job_id = started.json()["job_id"]

    for _ in range(JOB_POLL_ATTEMPTS):
        job = await admin.get(f"/generation-jobs/{job_id}")
        assert job.status_code == 200, job.text
        status = job.json()["status"]
        if status in ("published", "failed"):
            assert status == "published", job.json()
            break
        await asyncio.sleep(JOB_POLL_SECONDS)
    else:  # pragma: no cover
        pytest.fail("The v1 generation job never reached a terminal state")
    return course_id


@pytest.mark.asyncio
async def test_the_v1_generation_pipeline_still_publishes_a_real_course(
    admin: Actor, world: World, _flag_off: Path
) -> None:
    course_id = await _generate_v1_course(admin, world, _flag_off)

    detail = await admin.get(f"/courses/{course_id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["title"] == COURSE_TITLE
    assert len(body["modules"]) == 1
    module = body["modules"][0]
    assert module["title"] == "Recuento de caja"
    assert [lesson["title"] for lesson in module["lessons"]] == [
        "Recuento de apertura",
        "Recuento de cierre",
    ]
    # The exercise hangs off the module's last lesson, as v1 has always done.
    assert len(module["lessons"][1]["exercises"]) == 1
    assert module["lessons"][1]["exercises"][0]["type"] == "test"

    async with async_session_factory() as db:
        course = await db.get(Course, course_id)
        # Migration 0005's additive columns took their defaults; v1 semantics untouched.
        assert course.delivery_mode is CourseDeliveryMode.STATIC
        assert course.schema_status is CourseSchemaStatus.DRAFT
        assert course.schema_version == 1
        assert course.intent_density == 3
        assert course.schema_validated_by is None
        assert course.schema_validated_at is None
        # And the single decision point agrees.
        assert resolve_delivery(course, settings) == "static"
        # No v2 row was created by a v1 generation.
        nodes = (
            await db.execute(
                text("SELECT count(*) FROM course_nodes WHERE course_id = :cid"),
                {"cid": course_id},
            )
        ).scalar_one()
        assert nodes == 0

    published = await admin.post(f"/courses/{course_id}/publish")
    assert published.status_code == 200, published.text
    assert published.json()["status"] == ContentStatus.PUBLISHED.value


@pytest.mark.asyncio
async def test_the_v1_learner_journey_completes_and_grants_skills_at_medium(
    admin: Actor, employee: Actor, world: World, _flag_off: Path
) -> None:
    """The v1 closing rule, unchanged: every lesson visited, every exercise passed.

    And ``_assign_course_skills`` still grants ``medium``. B11 gave it an optional
    ``level``, defaulting to ``medium``, which the dynamic branch passes and v1 does
    not — this is the assertion that keeps the two apart.
    """
    course_id = await _generate_v1_course(admin, world, _flag_off)
    assert (await admin.post(f"/courses/{course_id}/publish")).status_code == 200

    async with async_session_factory() as db:
        lessons = (
            await db.execute(
                select(Lesson)
                .join(Module, Module.id == Lesson.module_id)
                .where(Module.course_id == course_id)
                .order_by(Lesson.position)
            )
        ).scalars().all()
        assert len(lessons) == 2
        lesson_ids = [lesson.id for lesson in lessons]
        exercise = (
            await db.execute(
                select(Exercise).where(Exercise.lesson_id == lesson_ids[1])
            )
        ).scalar_one()
        exercise_id = exercise.id
        # The auto-created skills v1 derives from the extracted themes.
        skill_names = (
            await db.execute(
                text("SELECT name FROM skills WHERE org_id = :org"), {"org": world.org.id}
            )
        ).scalars().all()
        assert "recuento_de_caja" in skill_names

    assigned = await admin.post(
        "/enrollments",
        json={"course_id": str(course_id), "user_ids": [str(world.employee.id)]},
    )
    assert assigned.status_code == 201, assigned.text
    enrollment_id = assigned.json()[0]["id"]
    assert assigned.json()[0]["status"] == EnrollmentStatus.ASSIGNED.value

    # First lesson: no exercises, so visiting it completes it and starts the enrollment.
    first = await employee.post(f"/lessons/{lesson_ids[0]}/complete")
    assert first.status_code == 200, first.text
    assert first.json()["completed"] is True

    # Second lesson has an exercise, so it is not complete until that is passed.
    second = await employee.post(f"/lessons/{lesson_ids[1]}/complete")
    assert second.status_code == 200, second.text
    assert second.json()["completed"] is False

    # Cannot complete the course yet either.
    premature = await employee.post(f"/enrollments/{enrollment_id}/complete")
    assert premature.status_code == 409, premature.text

    failed = await employee.post(
        f"/exercises/{exercise_id}/attempt", json={"answer": {"selected": EXERCISE_WRONG}}
    )
    assert failed.status_code == 200, failed.text
    assert failed.json()["passed"] is False
    assert failed.json()["score"] == pytest.approx(0.0)

    passed = await employee.post(
        f"/exercises/{exercise_id}/attempt",
        json={"answer": {"selected": EXERCISE_CORRECT}},
    )
    assert passed.status_code == 200, passed.text
    assert passed.json()["passed"] is True
    assert passed.json()["explanation"]

    attempts = await employee.get(f"/exercises/{exercise_id}/attempts")
    assert attempts.status_code == 200
    assert len(attempts.json()) == 2

    done = await employee.post(f"/lessons/{lesson_ids[1]}/complete")
    assert done.json()["completed"] is True

    progress = await employee.get(f"/enrollments/{enrollment_id}")
    assert progress.status_code == 200
    assert progress.json()["progress"] == pytest.approx(1.0)

    completed = await employee.post(f"/enrollments/{enrollment_id}/complete")
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == EnrollmentStatus.COMPLETED.value

    async with async_session_factory() as db:
        enrollment = (
            await db.execute(
                select(Enrollment).where(Enrollment.id == uuid.UUID(enrollment_id))
            )
        ).scalar_one()
        assert enrollment.status is EnrollmentStatus.COMPLETED
        assert enrollment.completed_at is not None
        assert float(enrollment.score or 0.0) == pytest.approx(1.0)

        skills = (
            await db.execute(
                select(UserSkill).where(UserSkill.user_id == world.employee.id)
            )
        ).scalars().all()
        assert skills, "v1 course completion granted no skill"
        # `medium`, the v1 level. The `mastery -> skill_level` translation of §3.3 is
        # dynamic-branch only and must not leak into this path.
        assert {row.level for row in skills} == {SkillLevel.MEDIUM}
        assert {row.source for row in skills} == {"course_completion"}

    mine = await employee.get("/users/me/skills")
    assert mine.status_code == 200
    assert [row["level"] for row in mine.json()] == ["medium"]


@pytest.mark.asyncio
async def test_a_course_flipped_to_dynamic_is_still_served_by_v1_with_the_flag_off(
    admin: Actor, employee: Actor, world: World, _flag_off: Path
) -> None:
    """The first line of ``resolve_delivery``, which is why it is one function.

    Somebody can set ``delivery_mode='dynamic'`` and ``schema_status='validated'`` in
    the database — a restored dump, a half-finished migration to v2, an operator who
    turned the flag off again. With the flag off the course goes back through v1, and
    the v2 routes stay gone.
    """
    course_id = await _generate_v1_course(admin, world, _flag_off)

    async with async_session_factory() as db:
        course = await db.get(Course, course_id)
        course.delivery_mode = CourseDeliveryMode.DYNAMIC
        course.schema_status = CourseSchemaStatus.VALIDATED
        await db.commit()
        assert resolve_delivery(course, settings) == "static"

    # The v1 detail route still returns the module tree.
    detail = await admin.get(f"/courses/{course_id}")
    assert detail.status_code == 200
    assert len(detail.json()["modules"]) == 1

    # And the v2 node list does not exist, flags beating course columns.
    assert (await employee.get(f"/courses/{course_id}/nodes")).status_code == 404


@pytest.mark.asyncio
async def test_the_v1_admin_surfaces_are_untouched(
    admin: Actor, world: World, _flag_off: Path
) -> None:
    """A sweep of the v1 admin routes the v2 batches touched around: documents,
    courses, lessons, exercises, stats, generation jobs."""
    documents = await admin.get("/documents")
    assert documents.status_code == 200
    assert any(row["id"] == str(world.document.id) for row in documents.json()["items"])

    course_id = await _generate_v1_course(admin, world, _flag_off)

    listing = await admin.get("/courses")
    assert listing.status_code == 200
    assert any(row["id"] == str(course_id) for row in listing.json()["items"])

    async with async_session_factory() as db:
        lesson = (
            await db.execute(
                select(Lesson)
                .join(Module, Module.id == Lesson.module_id)
                .where(Module.course_id == course_id)
                .order_by(Lesson.position)
            )
        ).scalars().first()
        lesson_id = lesson.id

    edited = await admin.put(
        f"/lessons/{lesson_id}", json={"title": "Recuento de apertura (revisado)"}
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["title"] == "Recuento de apertura (revisado)"

    renamed = await admin.put(f"/courses/{course_id}", json={"title": "Caja, v2 del titulo"})
    assert renamed.status_code == 200, renamed.text

    stats = await admin.get("/stats")
    assert stats.status_code == 200
    assert stats.json()["total_courses"] >= 1
    assert "recent_activity" in stats.json()

    archived = await admin.post(f"/courses/{course_id}/archive")
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == ContentStatus.ARCHIVED.value


__all__ = ["Actor", "World"]
