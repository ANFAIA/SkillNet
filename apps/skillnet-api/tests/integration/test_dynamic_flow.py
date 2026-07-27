"""The v2 vertical slice, end to end, against a real Postgres.

    schema proposed -> reviewed -> validated -> learner onboarded -> node opened ->
    probe -> render -> answer -> mastery -> next node -> course closed -> reopened

Every step goes through the HTTP surface of §11 with the real graphs, the real OpenUI
parser and the real SQL. Only two things are substituted, both by configuration rather
than by patching: the LLM (``LLM_MODEL=fixture/local`` -> ``FixtureLLMService``, §12.1)
and the embedder. There is no monkeypatched service and no fake repository anywhere in
this file — if a route stops committing, or a repository writes the wrong column, this
test fails and the unit suite does not.

**How to run it.** Needs a Postgres at ``DATABASE_URL`` (``docker compose up db``);
migrations are applied by the fixture. Excluded from the default
``pytest -m "not integration"``::

    docker compose up -d db
    uv run pytest -m integration tests/integration/test_dynamic_flow.py -v

**How the fixtures are keyed, and why that is the point.** ``FixtureLLMService`` looks a
recording up by ``sha256(system_prompt + user_prompt)``. This module therefore *rebuilds
every prompt with the production builders*, from values it reads back out of the
database, and registers the packaged responses under those keys. So a node that stops
threading ``available_headings``, ``effective_density``, ``scaffold_band`` or
``role_title`` into its prompt hashes to a different key, the LLM call raises, the graph
falls back to the seed lesson and the assertions on ``status='ready'`` fail loudly. The
alternative — a stub LLM returning a canned string for any prompt — would pass while the
pipeline silently stopped personalising anything.

What this file asserts that no unit test can:

* the design-time graph writes a real 4-node schema, prunes the cyclic prerequisite
  pair, and drops the invented heading with a warning;
* the gate is blocking: unreviewed nodes cannot be validated, a validated schema cannot
  be edited, and an employee gets ``404`` for a node whose course is not validated;
* ``answer_key`` never appears in any response body, in any of the four places it could
  leak (probe items, render, attempt result, render history);
* the mastery rule moves ``learner_node_states`` exactly as §7.3 says over a real
  sequence of answers, including the ceiling that makes a ``critical`` threshold
  reachable;
* §7.5 closes the enrollment when the last critical node closes — from a demonstrated
  node, from a probe verdict and from a waiver — and **reopens** it when the creator adds
  a new critical node, which is the recalculation §7.5 makes mandatory;
* the ``mastery -> user_skills`` bridge of §3.3 writes upwards, and §7.1 reads the prior
  back on the next node that shares the skill;
* the cache of §9.3 is real: a second learner in the same bucket is served the first
  one's render with ``cached: true`` and **no second generation**.
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

import src.llm as llm_package
from src.agents.content.helpers import estimate_pages, themes_list
from src.agents.runtime.nodes import load_source_context
from src.config import settings
from src.deps.auth import current_user
from src.deps.db import async_session_factory, engine
from src.llm.fixtures import write_fixture
from src.llm.parsing import parse_json_response
from src.llm.prompts import THEME_EXTRACTOR_SYSTEM, build_extraction_prompt
from src.llm.prompts.probe import PROBE_GENERATOR_SYSTEM, build_probe_prompt
from src.llm.prompts.runtime import (
    FORMAT_DECIDER_SYSTEM,
    build_format_prompt,
    build_ui_prompt,
    ui_generator_system,
)
from src.llm.prompts.schema import SCHEMA_DESIGNER_SYSTEM, build_schema_prompt
from src.main import create_app
from src.models import (
    Course,
    CourseNode,
    CourseSkill,
    Document,
    DocumentChunk,
    DocumentStatus,
    Enrollment,
    EnrollmentStatus,
    LearnerNodeState,
    LlmUsageLog,
    NodeRender,
    NodeRenderView,
    Organization,
    Skill,
    User,
    UserRole,
)
from src.models.user_skill import SkillLevel, UserSkill
from src.services.mastery_service import target_bloom, threshold_for
from src.services.node_render_service import build_render_key
from src.services.skill_service import mastery_to_level

pytestmark = pytest.mark.integration

API_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = Path(llm_package.__file__).parent / "fixture_data"
PREFIX = "/api/v1"

T = TypeVar("T")

# --- the source document ----------------------------------------------------------
#
# Short on purpose: <= 5 pages is the `full_text` branch of both `load_source` (§4.1)
# and `load_source_context` (§4.2), so the whole flow runs without needing semantic
# retrieval to be meaningful — which with `FixtureEmbeddingService` it is not (§12.1).
DOC_TITLE = "Politica de devoluciones"
DOC_FULL_TEXT = (
    "Politica de devoluciones\n\n"
    "El cliente dispone de 14 dias naturales desde la entrega para devolver un "
    "articulo sin dar explicaciones. Con el ticket de compra se reembolsa el importe; "
    "sin ticket se emite un vale.\n\n"
    "Excepciones\n\n"
    "Los articulos precintados de higiene y los personalizados no admiten devolucion. "
    "Un articulo defectuoso amplia el plazo a dos anos.\n\n"
    "Atencion al cliente\n\n"
    "Se explica el motivo de cada decision y no se atribuye la negativa a la politica "
    "sin mas."
)
#: The headings the chunker would have stored. This is the **closed list** the designer
#: prompt may choose from, which is why the packaged proposal's "Manual interno de tono"
#: has to be dropped: an invented heading matches no chunk, so the runtime would serve
#: content with no documentary basis.
DOC_HEADINGS = ("Devoluciones", "Plazo", "Excepciones", "Atencion al cliente")
INVENTED_HEADING = "Manual interno de tono"

COURSE_TITLE = "Politica de devoluciones"
COURSE_OUTCOME = "Gestionar una devolucion en mostrador sin errores"
INTENT_DENSITY = 3

ROLE_TITLE = "Dependiente"
SECTOR = "retail"

SKILL_NAME = "Gestion de devoluciones"

# Node titles the packaged `schema_design/returns_policy.json` proposal produces.
N_PLAZO = "Plazo de devolucion"
N_EXCEPCIONES = "Excepciones al plazo"
N_REGISTRO = "Registro de la devolucion"
N_TRATO = "Trato con el cliente"

#: The item the packaged `genera_ui/openui_exercise.txt` program carries, and its key.
QUIZ_ITEM_ID = "q1"
QUIZ_CORRECT = 1
QUIZ_WRONG = 0

#: Answers to the packaged probe (`probe_generate/plazo_devolucion.json`).
PROBE_A_CORRECT, PROBE_B_CORRECT, PROBE_C_CORRECT = 1, 2, "30"
PROBE_A_WRONG, PROBE_B_WRONG = 0, 0

RENDER_POLL_ATTEMPTS = 120
RENDER_POLL_SECONDS = 0.25
JOB_POLL_ATTEMPTS = 200


# --------------------------------------------------------------------------------- #
# Session helpers
# --------------------------------------------------------------------------------- #
def packaged(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def _run(coro: Awaitable[T]) -> T:
    return asyncio.run(coro)  # type: ignore[arg-type]


async def _probe_database() -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


@pytest.fixture(scope="module", autouse=True)
def _migrated_database() -> None:
    """Postgres at ``head``, or a skip that says what is missing.

    Sync on purpose: alembic's ``env.py`` calls ``asyncio.run`` itself, which cannot
    happen inside an already-running loop — the same reason
    ``tests/integration/test_migration_0005.py`` uses sync test functions.
    """
    try:
        _run(_probe_database())
    except Exception as exc:  # noqa: BLE001 - a missing DB is a skip, not a failure
        pytest.skip(f"No Postgres at DATABASE_URL ({type(exc).__name__}: {exc}).")
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    command.upgrade(config, "head")
    _run(engine.dispose())


@pytest.fixture(autouse=True)
def _fixture_llm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point every LLM and embedder construction site at recordings on disk.

    By configuration, through ``maybe_fixture_llm``: no service is patched, so the eight
    build sites of §12.1 are exercised as they are in production with
    ``LLM_MODEL=fixture/local`` — which is exactly the ``fixtures`` compose profile.
    """
    monkeypatch.setattr(settings, "DYNAMIC_COURSES_MODE", "on")
    monkeypatch.setattr(settings, "LLM_MODEL", "fixture/local")
    monkeypatch.setattr(settings, "EMBEDDING_MODEL", "fixture/local")
    monkeypatch.setattr(settings, "LLM_RUNTIME_FAST_MODEL", "fixture/local")
    monkeypatch.setattr(settings, "LLM_RUNTIME_HEAVY_MODEL", "fixture/local")
    monkeypatch.setattr(settings, "LLM_FIXTURE_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "LLM_FIXTURE_MODE", "replay")
    return tmp_path


class World:
    """The seeded rows plus the two clients that act on them."""

    def __init__(self, *, org: Organization, admin: User, employee: User, other: User,
                 document: Document, skill: Skill) -> None:
        self.org = org
        self.admin = admin
        self.employee = employee
        self.other = other
        self.document = document
        self.skill = skill
        self.course_id: uuid.UUID | None = None


async def _seed(fixture_dir: Path) -> World:
    """One org, one admin, two employees, one ingested document, one skill."""
    suffix = uuid.uuid4().hex[:8]
    async with async_session_factory() as db:
        org = Organization(name=f"Flow {suffix}", slug=f"flow-{suffix}", settings={"sector": SECTOR})
        db.add(org)
        await db.flush()

        admin = User(
            org_id=org.id,
            email=f"admin-{suffix}@flow.test",
            hashed_password="x",
            full_name="Admin de prueba",
            role=UserRole.ADMIN,
            is_active=True,
        )
        employee = User(
            org_id=org.id,
            email=f"empleado-{suffix}@flow.test",
            hashed_password="x",
            full_name="Empleada de prueba",
            role=UserRole.EMPLOYEE,
            is_active=True,
        )
        other = User(
            org_id=org.id,
            email=f"otro-{suffix}@flow.test",
            hashed_password="x",
            full_name="Otro empleado",
            role=UserRole.EMPLOYEE,
            is_active=True,
        )
        db.add_all([admin, employee, other])
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
            page_count=2,
        )
        db.add(document)
        await db.flush()

        # The chunks the ingester would have written. Their `heading` metadata is the
        # closed list `load_source` hands to the designer prompt; the embeddings are
        # deterministic fixture vectors and are never asserted on for relevance.
        from src.llm.embedding import resolve_embedding_config
        from src.llm.fixtures import maybe_fixture_embedder

        embedder = maybe_fixture_embedder(resolve_embedding_config({}))
        vectors = await embedder.embed_texts(list(DOC_HEADINGS), prefix="passage: ")
        for index, (heading, vector) in enumerate(zip(DOC_HEADINGS, vectors, strict=True)):
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=f"[Documento: {DOC_TITLE}] [Seccion: {heading}] {DOC_FULL_TEXT}",
                    chunk_metadata={"heading": heading},
                    embedding=vector,
                )
            )

        skill = Skill(org_id=org.id, name=f"{SKILL_NAME} {suffix}")
        db.add(skill)
        await db.commit()

    _register_design_fixtures(fixture_dir, document=document)
    return World(
        org=org, admin=admin, employee=employee, other=other,
        document=document, skill=skill,
    )


def _register_design_fixtures(directory: Path, *, document: Document) -> None:
    """The two design-time recordings, keyed on the prompts §4.1 must build."""
    write_fixture(
        system_prompt=THEME_EXTRACTOR_SYSTEM,
        user_prompt=build_extraction_prompt(DOC_FULL_TEXT),
        response=packaged("schema_design/returns_policy_themes.json"),
        relative_path="schema_design/returns_policy_themes.json",
        use_case="schema_design",
        directory=directory,
    )
    write_fixture(
        system_prompt=SCHEMA_DESIGNER_SYSTEM,
        user_prompt=build_schema_prompt(
            themes_list(parse_json_response(packaged("schema_design/returns_policy_themes.json"))),
            {
                "total_pages": estimate_pages(document),
                "doc_count": 1,
                "doc_titles": [DOC_TITLE],
            },
            list(DOC_HEADINGS),
            intent_density=INTENT_DENSITY,
            course_title=COURSE_TITLE,
            course_outcome=COURSE_OUTCOME,
        ),
        response=packaged("schema_design/returns_policy.json"),
        relative_path="schema_design/returns_policy.json",
        use_case="schema_design",
        directory=directory,
    )


async def _register_probe_fixtures(directory: Path, course_id: uuid.UUID) -> None:
    """The probe generator's recording, for every node of the course (§7.1 origin 3).

    Registered per node because ``build_probe_prompt`` carries the node's title, summary,
    outcome and criticality. The same response serves them all: what matters here is that
    the origin-3 path runs, writes the items back into ``course_nodes.probe_items`` and
    that the *next* learner therefore pays nothing.
    """
    async with async_session_factory() as db:
        nodes = (
            (await db.execute(select(CourseNode).where(CourseNode.course_id == course_id)))
            .scalars()
            .all()
        )
        for node in nodes:
            source_context = await load_source_context(db, node, node.org_id)
            write_fixture(
                system_prompt=PROBE_GENERATOR_SYSTEM,
                user_prompt=build_probe_prompt(
                    title=node.title,
                    summary=node.summary,
                    outcome=node.outcome,
                    criticality=str(getattr(node.criticality, "value", node.criticality)),
                    source_context=source_context,
                ),
                response=packaged("probe_generate/plazo_devolucion.json"),
                relative_path="probe_generate/plazo_devolucion.json",
                use_case="probe_generate",
                directory=directory,
            )


async def _register_render_fixtures(
    directory: Path, *, node_id: uuid.UUID, user_id: uuid.UUID, ui_format: str
) -> None:
    """Recordings for ``decide_formato`` and ``genera_ui`` for one (node, learner).

    Both prompts are rebuilt from the **live** rows the graph will read, using the same
    public builders ``src/agents/runtime/nodes.py`` uses. That is what makes this a test
    of the pipeline rather than of a stub: drop ``role_title`` from the prompt and the key
    changes, the fixture is not found, and the render comes back as ``fallback``.
    """
    from src.repositories.learner_profile_repo import LearnerProfileRepository
    from src.repositories.learner_node_state_repo import LearnerNodeStateRepository
    from src.services.node_render_service import runtime_model_key

    async with async_session_factory() as db:
        node = await db.get(CourseNode, node_id)
        assert node is not None
        course = await db.get(Course, node.course_id)
        assert course is not None
        user = await db.get(User, user_id)
        assert user is not None
        profile = await LearnerProfileRepository(db).get_by_user(user_id)
        node_state = await LearnerNodeStateRepository(db).get_by_user_and_node(
            user_id, node_id
        )
        org = await db.get(Organization, node.org_id)
        org_settings = dict(org.settings) if org and org.settings else {}
        source_context = await load_source_context(db, node, node.org_id)

        key = build_render_key(
            node=node,
            course=course,
            profile=profile,
            node_state=node_state,
            accessibility=dict(getattr(user, "accessibility", None) or {}),
            model_key=runtime_model_key(org_settings),
        )
        criticality = str(getattr(node.criticality, "value", node.criticality))
        default_format = str(
            getattr(node.default_ui_format, "value", node.default_ui_format)
        )
        mastery = float(getattr(node_state, "mastery", 0.0) or 0.0)
        threshold = threshold_for(criticality, node.mastery_threshold)

        # `decide_formato` is skipped entirely while the learner is calibrating (§6.4),
        # so this recording only matters once `nodes_completed >= 3`. Registered anyway:
        # a graph that called the decider during calibration would find it and the
        # calibration assertion elsewhere in this file would be the one to fail, which is
        # a clearer signal than a missing fixture.
        write_fixture(
            system_prompt=FORMAT_DECIDER_SYSTEM,
            user_prompt=build_format_prompt(
                title=node.title,
                summary=node.summary,
                outcome=node.outcome,
                criticality=criticality,
                default_ui_format=default_format,
                role_title=getattr(profile, "role_title", None),
                sector=getattr(profile, "sector", None),
                experience_level=str(
                    getattr(
                        getattr(profile, "experience_level", None), "value", "unknown"
                    )
                ),
                preset=str(getattr(getattr(profile, "preset", None), "value", "standard")),
                effective_density=key.effective_density,
                scaffold_band=key.scaffold_band,
                vector_bucket=key.vector_bucket,
                mastery=mastery,
                consecutive_failed=int(
                    getattr(node_state, "consecutive_failed", 0) or 0
                ),
                last_error_kind=_plain_or_none(
                    getattr(node_state, "last_error_kind", None)
                ),
                source_has_numbers=any(char.isdigit() for char in source_context),
            ),
            response=json.dumps(
                {"ui_format": ui_format, "rationale": "fixture"}, ensure_ascii=False
            ),
            relative_path=f"decide_formato/{ui_format}.json",
            use_case="decide_formato",
            directory=directory,
        )
        write_fixture(
            system_prompt=ui_generator_system(),
            user_prompt=build_ui_prompt(
                title=node.title,
                summary=node.summary,
                outcome=node.outcome,
                criticality=criticality,
                ui_format=ui_format,
                effective_density=key.effective_density,
                scaffold_band=key.scaffold_band,
                role_title=getattr(profile, "role_title", None),
                sector=getattr(profile, "sector", None),
                experience_level=str(
                    getattr(
                        getattr(profile, "experience_level", None), "value", "unknown"
                    )
                ),
                preset=str(getattr(getattr(profile, "preset", None), "value", "standard")),
                target_bloom=target_bloom(mastery, threshold),
                last_error_kind=_plain_or_none(
                    getattr(node_state, "last_error_kind", None)
                ),
                consecutive_failed=int(
                    getattr(node_state, "consecutive_failed", 0) or 0
                ),
                consecutive_correct=int(
                    getattr(node_state, "consecutive_correct", 0) or 0
                ),
                tutor_signals=(),
                source_context=source_context,
            ),
            response=packaged(f"genera_ui/openui_{ui_format}.txt"),
            relative_path=f"genera_ui/openui_{ui_format}.txt",
            use_case="genera_ui",
            directory=directory,
        )


def _plain_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


async def _cleanup(world: World) -> None:
    """Drop everything this test created, in FK order."""
    async with async_session_factory() as db:
        if world.course_id is not None:
            await db.execute(
                text("DELETE FROM node_render_views WHERE render_id IN "
                     "(SELECT id FROM node_renders WHERE node_id IN "
                     "(SELECT id FROM course_nodes WHERE course_id = :cid))"),
                {"cid": world.course_id},
            )
            for table in (
                "node_attempts",
                "node_feedback",
                "node_probes",
                "learner_node_states",
                "node_renders",
            ):
                await db.execute(
                    text(f"DELETE FROM {table} WHERE node_id IN "
                         "(SELECT id FROM course_nodes WHERE course_id = :cid)"),
                    {"cid": world.course_id},
                )
            await db.execute(
                text("DELETE FROM course_node_prerequisites WHERE node_id IN "
                     "(SELECT id FROM course_nodes WHERE course_id = :cid)"),
                {"cid": world.course_id},
            )
            await db.execute(
                text("DELETE FROM course_nodes WHERE course_id = :cid"),
                {"cid": world.course_id},
            )
        await db.execute(
            text("DELETE FROM learning_events WHERE user_id = ANY(:ids)"),
            {"ids": [world.employee.id, world.other.id]},
        )
        await db.execute(
            text("DELETE FROM learner_profiles WHERE user_id = ANY(:ids)"),
            {"ids": [world.employee.id, world.other.id]},
        )
        await db.execute(
            text("DELETE FROM llm_usage_log WHERE org_id = :org"), {"org": world.org.id}
        )
        await db.execute(
            text("DELETE FROM audit_log WHERE org_id = :org"), {"org": world.org.id}
        )
        await db.execute(
            text("DELETE FROM user_skills WHERE user_id = ANY(:ids)"),
            {"ids": [world.employee.id, world.other.id, world.admin.id]},
        )
        await db.execute(
            text("DELETE FROM enrollments WHERE user_id = ANY(:ids)"),
            {"ids": [world.employee.id, world.other.id]},
        )
        if world.course_id is not None:
            await db.execute(
                text("DELETE FROM course_skills WHERE course_id = :cid"),
                {"cid": world.course_id},
            )
            await db.execute(
                text("DELETE FROM generation_jobs WHERE result_course_id = :cid"),
                {"cid": world.course_id},
            )
            await db.execute(
                text("DELETE FROM courses WHERE id = :cid"), {"cid": world.course_id}
            )
        await db.execute(
            text("DELETE FROM skills WHERE org_id = :org"), {"org": world.org.id}
        )
        await db.execute(
            text("DELETE FROM document_chunks WHERE document_id = :doc"),
            {"doc": world.document.id},
        )
        await db.execute(
            text("DELETE FROM documents WHERE id = :doc"), {"doc": world.document.id}
        )
        await db.execute(
            text("DELETE FROM users WHERE org_id = :org"), {"org": world.org.id}
        )
        await db.execute(
            text("DELETE FROM organizations WHERE id = :org"), {"org": world.org.id}
        )
        await db.commit()


@pytest_asyncio.fixture
async def world(_fixture_llm: Path) -> AsyncIterator[World]:
    seeded = await _seed(_fixture_llm)
    try:
        yield seeded
    finally:
        await _cleanup(seeded)


class Actor:
    """An ``AsyncClient`` bound to one seeded user.

    The session-cookie backend is replaced by a dependency override of
    ``current_user`` — the *only* substitution in the request path. Logging in with
    fastapi-users would test password hashing, which has its own tests and nothing to do
    with §7.
    """

    def __init__(self, user: User) -> None:
        self.user = user
        self.app = create_app()
        self.app.dependency_overrides[current_user] = lambda: user
        self.client = AsyncClient(
            transport=ASGITransport(app=self.app), base_url="http://flow.test"
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def get(self, path: str, **kw: Any) -> Any:
        return await self.client.get(f"{PREFIX}{path}", **kw)

    async def post(self, path: str, **kw: Any) -> Any:
        return await self.client.post(f"{PREFIX}{path}", **kw)

    async def put(self, path: str, **kw: Any) -> Any:
        return await self.client.put(f"{PREFIX}{path}", **kw)

    async def delete(self, path: str, **kw: Any) -> Any:
        return await self.client.delete(f"{PREFIX}{path}", **kw)


@pytest_asyncio.fixture
async def admin(world: World) -> AsyncIterator[Actor]:
    actor = Actor(world.admin)
    try:
        yield actor
    finally:
        await actor.close()


@pytest_asyncio.fixture
async def learner(world: World) -> AsyncIterator[Actor]:
    actor = Actor(world.employee)
    try:
        yield actor
    finally:
        await actor.close()


@pytest_asyncio.fixture
async def second_learner(world: World) -> AsyncIterator[Actor]:
    actor = Actor(world.other)
    try:
        yield actor
    finally:
        await actor.close()


# --------------------------------------------------------------------------------- #
# Flow steps, reused by the tests below
# --------------------------------------------------------------------------------- #
async def propose_and_wait(admin: Actor, world: World) -> dict:
    """v1 ``POST /courses`` + v2 propose, waited out through the job endpoint."""
    created = await admin.post(
        "/courses",
        json={
            "title": COURSE_TITLE,
            "outcome": COURSE_OUTCOME,
            "source_document_id": str(world.document.id),
        },
    )
    assert created.status_code == 201, created.text
    world.course_id = uuid.UUID(created.json()["id"])

    accepted = await admin.post(
        f"/courses/{world.course_id}/schema/propose",
        json={"intent_density": INTENT_DENSITY},
    )
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["job_id"]

    for _ in range(JOB_POLL_ATTEMPTS):
        job = await admin.get(f"/generation-jobs/{job_id}")
        assert job.status_code == 200, job.text
        status = job.json()["status"]
        if status in ("schema_proposed", "failed"):
            assert status == "schema_proposed", job.json()
            break
        await asyncio.sleep(RENDER_POLL_SECONDS)
    else:  # pragma: no cover - a hung designer job
        pytest.fail("The schema proposal job never reached a terminal state")

    schema = await admin.get(f"/courses/{world.course_id}/schema")
    assert schema.status_code == 200, schema.text
    return schema.json()


def node_by_title(schema: dict, title: str) -> dict:
    for node in schema["nodes"]:
        if node["title"] == title:
            return node
    raise AssertionError(f"No node titled {title!r} in {[n['title'] for n in schema['nodes']]}")


async def review_all_and_validate(admin: Actor, world: World, schema: dict) -> dict:
    for node in schema["nodes"]:
        marked = await admin.post(
            f"/courses/{world.course_id}/schema/nodes/{node['id']}/review"
        )
        assert marked.status_code == 200, marked.text
    validated = await admin.post(f"/courses/{world.course_id}/schema/validate")
    assert validated.status_code == 200, validated.text
    return validated.json()


async def onboard(learner: Actor) -> dict:
    questions = await learner.get("/onboarding")
    assert questions.status_code == 200, questions.text
    body = questions.json()
    assert [q["id"] for q in body["questions"]] == [
        "role_title",
        "goal",
        "experience_level",
        "preset",
        "accessibility",
    ]
    # The art. 13 notice ships from the server, not from the wizard (§3.3).
    assert "proveedor de IA" in body["notice"]
    # Suggestions follow the org's sector.
    assert ROLE_TITLE in body["questions"][0]["suggestions"]

    submitted = await learner.post(
        "/onboarding",
        json={
            "role_title": ROLE_TITLE,
            "goal": "assigned",
            "experience_level": "some",
            "preset": "standard",
            "accessibility": {
                "short_blocks": False,
                "reduce_motion": False,
                "high_contrast": False,
                "extra_time": False,
            },
        },
    )
    assert submitted.status_code == 200, submitted.text
    return submitted.json()


async def enroll(admin: Actor, world: World, user: User) -> uuid.UUID:
    created = await admin.post(
        "/enrollments",
        json={"course_id": str(world.course_id), "user_ids": [str(user.id)]},
    )
    assert created.status_code == 201, created.text
    return uuid.UUID(created.json()[0]["id"])


async def wait_for_render(learner: Actor, node_id: uuid.UUID) -> dict:
    """Poll ``GET /nodes/{id}/render`` until the pinned render appears."""
    for _ in range(RENDER_POLL_ATTEMPTS):
        response = await learner.get(f"/nodes/{node_id}/render")
        if response.status_code == 200:
            return response.json()
        assert response.status_code == 202, response.text
        assert response.json()["status"] in ("pending", "generating")
        await asyncio.sleep(RENDER_POLL_SECONDS)
    pytest.fail("The render never got pinned")  # pragma: no cover


async def generate_render(
    learner: Actor, world: World, node_id: uuid.UUID, *, ui_format: str, force: bool = False
) -> dict:
    await _register_render_fixtures(
        Path(settings.LLM_FIXTURE_DIR),
        node_id=node_id,
        user_id=learner.user.id,
        ui_format=ui_format,
    )
    accepted = await learner.post(f"/nodes/{node_id}/render", json={"force": force})
    assert accepted.status_code == 202, accepted.text
    return await wait_for_render(learner, node_id)


async def answer_quiz(
    learner: Actor, node_id: uuid.UUID, render_id: str, answer: int
) -> dict:
    response = await learner.post(
        f"/nodes/{node_id}/answer",
        json={
            "render_id": render_id,
            "item_id": QUIZ_ITEM_ID,
            "answer": {"selected": answer},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def state_of(user_id: uuid.UUID, node_id: uuid.UUID) -> LearnerNodeState | None:
    async with async_session_factory() as db:
        return (
            await db.execute(
                select(LearnerNodeState).where(
                    LearnerNodeState.user_id == user_id,
                    LearnerNodeState.node_id == node_id,
                )
            )
        ).scalar_one_or_none()


async def enrollment_of(user_id: uuid.UUID, course_id: uuid.UUID) -> Enrollment:
    async with async_session_factory() as db:
        row = (
            await db.execute(
                select(Enrollment).where(
                    Enrollment.user_id == user_id, Enrollment.course_id == course_id
                )
            )
        ).scalar_one_or_none()
        assert row is not None
        return row


def leaks_answer_key(payload: Any) -> bool:
    """Whether any answer-bearing key appears anywhere in a response body."""
    blob = json.dumps(payload, default=str)
    return any(
        marker in blob
        for marker in ('"answer_key"', '"correct"', '"correct_order"', '"blanks"', '"rubric"')
    )


# --------------------------------------------------------------------------------- #
# 1. Design time: propose -> review -> validate
# --------------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_the_designer_writes_a_real_schema_and_the_gate_blocks_until_reviewed(
    admin: Actor, learner: Actor, world: World
) -> None:
    schema = await propose_and_wait(admin, world)

    assert schema["schema_status"] == "proposed"
    # §10.1: proposing does not make a course dynamic. Only `validate` does.
    assert schema["delivery_mode"] == "static"
    titles = [node["title"] for node in schema["nodes"]]
    assert titles == [N_PLAZO, N_EXCEPCIONES, N_REGISTRO, N_TRATO]
    assert [node["position"] for node in schema["nodes"]] == [1, 2, 3, 4]
    assert [node["criticality"] for node in schema["nodes"]] == [
        "critical",
        "recommended",
        "critical",
        "contextual",
    ]
    # Thresholds derive from criticality (§3.2).
    assert node_by_title(schema, N_PLAZO)["mastery_threshold"] == pytest.approx(0.90)
    assert node_by_title(schema, N_TRATO)["mastery_threshold"] == pytest.approx(0.70)

    # The proposal asks for `Excepciones <- [Plazo, Registro]` and
    # `Registro <- [Excepciones]`, which is a 2-cycle. It must be pruned, not fatal.
    excepciones = node_by_title(schema, N_EXCEPCIONES)
    registro = node_by_title(schema, N_REGISTRO)
    edges = {
        excepciones["id"]: set(excepciones["prerequisite_node_ids"]),
        registro["id"]: set(registro["prerequisite_node_ids"]),
    }
    assert not (
        registro["id"] in edges[excepciones["id"]]
        and excepciones["id"] in edges[registro["id"]]
    ), "the cyclic prerequisite pair survived"
    assert node_by_title(schema, N_PLAZO)["id"] in edges[excepciones["id"]]

    # The invented heading is dropped, loudly.
    assert INVENTED_HEADING not in node_by_title(schema, N_TRATO)["source_headings"]
    assert any(INVENTED_HEADING in warning for warning in schema["warnings"])
    assert all(node["reviewed_at"] is None for node in schema["nodes"])

    # The employee surface does not exist for a course that is not validated.
    assert (await learner.get(f"/courses/{world.course_id}/nodes")).status_code == 404
    node_id = node_by_title(schema, N_PLAZO)["id"]
    assert (await learner.post(f"/nodes/{node_id}/render")).status_code == 404

    # The gate: no validation while a single node is unreviewed.
    refused = await admin.post(f"/courses/{world.course_id}/schema/validate")
    assert refused.status_code == 422, refused.text
    detail = refused.json()["detail"]
    assert detail["error"] == "unreviewed_nodes"
    assert len(detail["node_ids"]) == 4

    validated = await review_all_and_validate(admin, world, schema)
    assert validated["schema_status"] == "validated"
    assert validated["delivery_mode"] == "dynamic"
    assert validated["validated_by"] == str(world.admin.id)

    # And now the schema is locked: editing a live course takes an explicit step.
    locked = await admin.put(
        f"/courses/{world.course_id}/schema",
        json={"nodes": [
            {
                "id": node["id"],
                "title": node["title"],
                "summary": node["summary"],
                "criticality": node["criticality"],
                "position": node["position"],
                "default_ui_format": node["default_ui_format"],
                "source_headings": node["source_headings"],
                "prerequisite_node_ids": node["prerequisite_node_ids"],
            }
            for node in validated["nodes"]
        ]},
    )
    assert locked.status_code == 422, locked.text
    assert locked.json()["detail"]["error"] == "schema_locked"


# --------------------------------------------------------------------------------- #
# 2. The whole slice
# --------------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_the_full_learner_journey_closes_the_course(
    admin: Actor, learner: Actor, world: World
) -> None:
    schema = await propose_and_wait(admin, world)
    validated = await review_all_and_validate(admin, world, schema)
    plazo = uuid.UUID(node_by_title(validated, N_PLAZO)["id"])
    registro = uuid.UUID(node_by_title(validated, N_REGISTRO)["id"])
    await _register_probe_fixtures(Path(settings.LLM_FIXTURE_DIR), world.course_id)

    # The node carries a skill, and the org already verified the learner at `low`. That
    # is the §7.1 prior: 0.25 rather than everybody starting at zero.
    async with async_session_factory() as db:
        node = await db.get(CourseNode, plazo)
        node.skill_id = world.skill.id
        db.add(CourseSkill(course_id=world.course_id, skill_id=world.skill.id))
        db.add(
            UserSkill(
                user_id=world.employee.id,
                skill_id=world.skill.id,
                level=SkillLevel.LOW,
                source="peer_review",
            )
        )
        await db.commit()

    profile = await onboard(learner)
    assert profile["onboarding_completed_at"] is not None
    assert profile["role_title"] == ROLE_TITLE
    assert profile["sector"] == SECTOR
    assert profile["nodes_completed"] == 0

    enrollment_id = await enroll(admin, world, world.employee)

    # --- the node list -------------------------------------------------------------
    listing = await learner.get(f"/courses/{world.course_id}/nodes")
    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert body["delivery_mode"] == "dynamic"
    assert len(body["nodes"]) == 4
    assert body["can_complete"] is False
    # Only the two `critical` nodes block; `recommended` and `contextual` never do.
    assert set(body["blocked_by"]) == {str(plazo), str(registro)}
    assert body["progress_percent"] == 0
    first = next(row for row in body["nodes"] if row["id"] == str(plazo))
    assert first["locked"] is False and first["locked_by"] == []
    assert first["state"] == "not_started"

    # --- the probe: the productive wait of §9.1 ------------------------------------
    probe = await learner.post(f"/nodes/{plazo}/probe")
    assert probe.status_code == 200, probe.text
    session = probe.json()
    assert session["diagnostic"] is False  # `experience_level == 'some'`
    assert session["probe"]["scored"] is True
    # A `critical` node always serves the constructed tie-break item (§7.1).
    assert [item["item_id"] for item in session["items"]] == ["a", "b", "c"]
    assert not leaks_answer_key(session), "the probe served its own answer key"
    probe_id = session["probe"]["id"]

    # Transition 1 of §7.3: `probing`, and `mastery` seeded from `user_skills`.
    opened = await state_of(world.employee.id, plazo)
    assert str(getattr(opened.state, "value", opened.state)) == "probing"
    assert float(opened.mastery) == pytest.approx(0.25)

    # Origin 3 wrote the items back onto the node, so the next learner pays nothing.
    async with async_session_factory() as db:
        stored = await db.get(CourseNode, plazo)
        assert len(stored.probe_items or []) == 3
        assert set((stored.probe_answer_key or {})) == {"a", "b", "c"}

    # Fail the "apply" item: §7.2 rule 1 says mastery is then impossible, whatever
    # else happens.
    wrong_a = await learner.post(
        f"/nodes/{plazo}/probe/answer",
        json={"probe_id": probe_id, "item_id": "a", "answer": {"selected": PROBE_A_WRONG}},
    )
    assert wrong_a.status_code == 200, wrong_a.text
    assert wrong_a.json()["passed"] is False
    wrong_b = await learner.post(
        f"/nodes/{plazo}/probe/answer",
        json={"probe_id": probe_id, "item_id": "b", "answer": {"selected": PROBE_B_WRONG}},
    )
    assert wrong_b.status_code == 200, wrong_b.text
    closed = wrong_b.json()
    assert closed["verdict"] == "learning"
    assert closed["estimate"] == pytest.approx(0.0)
    # §9.1: the client is told to start the render now, not the server.
    assert closed["render_hint"] == "prefetch"

    learning = await state_of(world.employee.id, plazo)
    assert str(getattr(learning.state, "value", learning.state)) == "learning"
    # §7.3 rule 5: `probe_score` is written, `mastery` keeps the prior.
    assert float(learning.probe_score) == pytest.approx(0.0)
    assert float(learning.mastery) == pytest.approx(0.25)
    # `scaffold_band` is frozen here and nowhere else (§3.3).
    assert str(getattr(learning.scaffold_band, "value", learning.scaffold_band)) == "novice"

    # --- the render ----------------------------------------------------------------
    render = await generate_render(learner, world, plazo, ui_format="exercise")
    assert render["status"] == "ready", render
    assert render["backend"] == "openui"
    assert render["ui_format"] == "exercise"
    # The browser receives re-serialized dialect text, never a spec and never the
    # model's own bytes (§5.1, §5.5).
    assert isinstance(render["program"], str)
    assert "QuizItem(" in render["program"]
    assert "ui_spec" not in render and "spec" not in render and "raw_dsl" not in render
    assert not leaks_answer_key(render), "the render leaked the answer key"
    render_id = render["render_id"]

    async with async_session_factory() as db:
        stored_render = await db.get(NodeRender, uuid.UUID(render_id))
        # The IR and the key are persisted for audit and grading, server-side only.
        assert stored_render.ui_spec["components"]
        assert QUIZ_ITEM_ID in (stored_render.answer_key or {})
        # The learner's own view is recorded, which is what "ver la version anterior"
        # reads from (§5.5).
        views = (
            await db.execute(
                select(NodeRenderView).where(
                    NodeRenderView.render_id == stored_render.id,
                    NodeRenderView.user_id == world.employee.id,
                )
            )
        ).scalars().all()
        assert len(views) == 1
        usage = (
            await db.execute(
                select(LlmUsageLog).where(
                    LlmUsageLog.org_id == world.org.id,
                    LlmUsageLog.use_case == "genera_ui",
                )
            )
        ).scalars().all()
        assert usage, "genera_ui was not logged in llm_usage_log"
        assert all(row.duration_ms is not None for row in usage)

    # §6.4: no `decide_formato` call at all while calibrating.
    async with async_session_factory() as db:
        decided = (
            await db.execute(
                select(LlmUsageLog).where(
                    LlmUsageLog.org_id == world.org.id,
                    LlmUsageLog.use_case == "decide_formato",
                )
            )
        ).scalars().all()
        assert decided == [], "the format decider ran during the calibration period"

    history = await learner.get(f"/nodes/{plazo}/renders")
    assert history.status_code == 200
    assert [item["render_id"] for item in history.json()["renders"]] == [render_id]
    assert not leaks_answer_key(history.json())

    # --- answering: §7.3 and §7.4 --------------------------------------------------
    failed = await answer_quiz(learner, plazo, render_id, QUIZ_WRONG)
    assert failed["passed"] is False
    assert failed["correct_answer"] is None, "a failed answer revealed the key"
    assert failed["state"] == "learning"
    assert failed["consecutive_failed"] == 1
    # A failure never raises mastery (§7.3).
    assert failed["mastery"] <= 0.25

    # `attempt-before-hint` is satisfied now, so one hint is available.
    hint = await learner.post(
        f"/nodes/{plazo}/hint", json={"render_id": render_id, "item_id": QUIZ_ITEM_ID}
    )
    assert hint.status_code == 200, hint.text
    assert hint.json()["hints_used"] == 1
    assert hint.json()["hints_remaining"] == 2

    # Three correct answers in a row: the streak *and* the ceiling of §7.3, which is what
    # makes a 0.90 threshold reachable at all.
    results = [await answer_quiz(learner, plazo, render_id, QUIZ_CORRECT) for _ in range(3)]
    assert [row["passed"] for row in results] == [True, True, True]
    assert [row["consecutive_correct"] for row in results] == [1, 2, 3]
    assert results[-1]["state"] == "mastered"
    assert results[-1]["mastery"] >= 0.90
    assert results[-1]["next"] == "next_node"
    # Passing reveals the worked answer; that is the only path that does.
    assert results[0]["correct_answer"]["correct"] == QUIZ_CORRECT

    mastered = await state_of(world.employee.id, plazo)
    assert str(getattr(mastered.state, "value", mastered.state)) == "mastered"
    assert mastered.mastered_at is not None

    # §3.3: mastery translated into `user_skills`, upwards only, and the peer-verified
    # `low` is raised rather than replaced by a lower value.
    async with async_session_factory() as db:
        skill_row = (
            await db.execute(
                select(UserSkill).where(
                    UserSkill.user_id == world.employee.id,
                    UserSkill.skill_id == world.skill.id,
                )
            )
        ).scalar_one()
        assert skill_row.level is mastery_to_level(float(mastered.mastery))
        assert skill_row.level is SkillLevel.HIGH
        assert skill_row.source == "node_mastery"

    # `nodes_completed` moves only here (rule 6), never on a probe skip.
    profile_now = await learner.get("/users/me/learner-profile")
    assert profile_now.status_code == 200
    assert profile_now.json()["nodes_completed"] == 1

    # One critical node left, so the course is not done and says which one.
    listing = (await learner.get(f"/courses/{world.course_id}/nodes")).json()
    assert listing["can_complete"] is False
    assert listing["blocked_by"] == [str(registro)]
    assert listing["progress_percent"] == 50
    assert (await enrollment_of(world.employee.id, world.course_id)).status == (
        EnrollmentStatus.ASSIGNED
    )

    # --- the second node, mastered by the probe alone -------------------------------
    #
    # A `critical` node cannot be mastered from selected-response items (1/16 chance),
    # so 2/2 gives `tiebreak` and the constructed item decides. This also exercises the
    # §7.5 close from `POST /probe/answer`.
    probe2 = await learner.post(f"/nodes/{registro}/probe")
    assert probe2.status_code == 200, probe2.text
    probe2_id = probe2.json()["probe"]["id"]
    ok_a = await learner.post(
        f"/nodes/{registro}/probe/answer",
        json={"probe_id": probe2_id, "item_id": "a", "answer": {"selected": PROBE_A_CORRECT}},
    )
    assert ok_a.json()["passed"] is True
    ok_b = await learner.post(
        f"/nodes/{registro}/probe/answer",
        json={"probe_id": probe2_id, "item_id": "b", "answer": {"selected": PROBE_B_CORRECT}},
    )
    assert ok_b.json()["verdict"] == "tiebreak", ok_b.json()
    assert ok_b.json()["next_item_id"] == "c"
    ok_c = await learner.post(
        f"/nodes/{registro}/probe/answer",
        json={"probe_id": probe2_id, "item_id": "c", "answer": {"answer": PROBE_C_CORRECT}},
    )
    assert ok_c.status_code == 200, ok_c.text
    assert ok_c.json()["verdict"] == "mastered", ok_c.json()
    assert ok_c.json()["render_hint"] == "skip"

    skipped = await state_of(world.employee.id, registro)
    assert str(getattr(skipped.state, "value", skipped.state)) == "mastered"

    # A probe skip does NOT count towards calibration (§3.3): the node produced no
    # interaction events, so counting it would leave the learner with an empty vector.
    assert (await learner.get("/users/me/learner-profile")).json()["nodes_completed"] == 1

    # --- §7.5: the course closes itself --------------------------------------------
    closed_enrollment = await enrollment_of(world.employee.id, world.course_id)
    assert closed_enrollment.status is EnrollmentStatus.COMPLETED
    assert closed_enrollment.completed_at is not None
    expected_score = (float(mastered.mastery) + float(skipped.mastery)) / 2
    assert float(closed_enrollment.score) == pytest.approx(expected_score)
    assert closed_enrollment.id == enrollment_id

    listing = (await learner.get(f"/courses/{world.course_id}/nodes")).json()
    assert listing["can_complete"] is True
    assert listing["blocked_by"] == []
    assert listing["progress_percent"] == 100

    # The course's own skills were granted at the translated level, never downgraded.
    async with async_session_factory() as db:
        rows = (
            await db.execute(
                select(UserSkill).where(UserSkill.user_id == world.employee.id)
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].level is SkillLevel.HIGH

    # --- end-of-node feedback and instrumentation ---------------------------------
    feedback = await learner.post(
        f"/nodes/{plazo}/feedback", json={"difficulty": "hard", "unclear": "el plazo"}
    )
    assert feedback.status_code == 204
    events = await learner.post(
        f"/nodes/{plazo}/events",
        json={"events": [
            {"type": "block_dwell", "element": "text", "ms": 4000},
            {"type": "exercise_attempt", "element": "quiz"},
        ]},
    )
    assert events.status_code == 204


# --------------------------------------------------------------------------------- #
# 3. §7.5's mandatory recalculation
# --------------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_adding_a_critical_node_reopens_a_completed_enrollment(
    admin: Actor, learner: Actor, world: World
) -> None:
    """The half of §7.5 that has no UI: a schema change re-decides every enrollment.

    Without it, enrollment status would be a function of a schema that no longer exists —
    and "completed" is what a certificate prints.
    """
    schema = await propose_and_wait(admin, world)
    validated = await review_all_and_validate(admin, world, schema)
    await _register_probe_fixtures(Path(settings.LLM_FIXTURE_DIR), world.course_id)
    await onboard(learner)
    await enroll(admin, world, world.employee)

    # Shortcut to a completed course: waive both critical nodes. `waive` needs a state
    # row, which opening the probe creates — and this is also the §7.4 human path.
    critical = [n for n in validated["nodes"] if n["criticality"] == "critical"]
    assert len(critical) == 2
    for node in critical:
        assert (await learner.post(f"/nodes/{node['id']}/probe")).status_code == 200
        waived = await admin.post(
            f"/nodes/{node['id']}/waive",
            json={"user_id": str(world.employee.id), "reason": "la he visto hacerlo"},
        )
        assert waived.status_code == 200, waived.text
        assert waived.json()["state"] == "mastered"

    completed = await enrollment_of(world.employee.id, world.course_id)
    assert completed.status is EnrollmentStatus.COMPLETED
    # A waiver is an accreditation, not a measurement: `mastery` is left alone, so the
    # score is honest about having no number behind it.
    assert float(completed.score or 0.0) == pytest.approx(0.0)

    # Now the creator changes the critical set.
    unvalidated = await admin.post(f"/courses/{world.course_id}/schema/unvalidate")
    assert unvalidated.status_code == 200, unvalidated.text
    assert unvalidated.json()["schema_status"] == "proposed"
    # Unvalidating takes the course out of v2 in the same transaction (§11.1 lock 2).
    assert unvalidated.json()["delivery_mode"] == "static"
    assert (await learner.get(f"/courses/{world.course_id}/nodes")).status_code == 404

    nodes_payload = [
        {
            "id": node["id"],
            "title": node["title"],
            "summary": node["summary"],
            "outcome": node["outcome"],
            "criticality": node["criticality"],
            "position": node["position"],
            "default_ui_format": node["default_ui_format"],
            "source_headings": node["source_headings"],
            "prerequisite_node_ids": node["prerequisite_node_ids"],
        }
        for node in unvalidated.json()["nodes"]
    ]
    nodes_payload.append(
        {
            "title": "Reembolso por transferencia",
            "summary": "El reembolso a una tarjeta cancelada se hace por transferencia.",
            "criticality": "critical",
            "position": 5,
            "default_ui_format": "explanation",
            "source_headings": ["Devoluciones"],
            "prerequisite_node_ids": [],
        }
    )
    updated = await admin.put(
        f"/courses/{world.course_id}/schema", json={"nodes": nodes_payload}
    )
    assert updated.status_code == 200, updated.text
    assert len(updated.json()["nodes"]) == 5

    # The PUT itself recomputes: a new critical node nobody has mastered reopens the row.
    reopened = await enrollment_of(world.employee.id, world.course_id)
    assert reopened.status is EnrollmentStatus.IN_PROGRESS
    assert reopened.completed_at is None

    # Archiving it again closes the course back up — the other direction of §7.5.
    for node in nodes_payload:
        if node.get("title") == "Reembolso por transferencia":
            node["id"] = next(
                row["id"] for row in updated.json()["nodes"]
                if row["title"] == "Reembolso por transferencia"
            )
            node["archived"] = True
    archived = await admin.put(
        f"/courses/{world.course_id}/schema", json={"nodes": nodes_payload}
    )
    assert archived.status_code == 200, archived.text
    closed_again = await enrollment_of(world.employee.id, world.course_id)
    assert closed_again.status is EnrollmentStatus.COMPLETED


# --------------------------------------------------------------------------------- #
# 4. The cache: the operational meaning of "pays no tokens"
# --------------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_second_learner_in_the_same_bucket_is_served_from_the_cache(
    admin: Actor, learner: Actor, second_learner: Actor, world: World
) -> None:
    """§9.3 level 3, measured: same bucket -> same ``cache_key`` -> zero generation.

    The key deliberately excludes ``user_id``, so this is a *design* claim rather than an
    accident, and the assertion that matters is the second one: **no new
    ``node_renders`` row**.
    """
    schema = await propose_and_wait(admin, world)
    validated = await review_all_and_validate(admin, world, schema)
    await _register_probe_fixtures(Path(settings.LLM_FIXTURE_DIR), world.course_id)
    trato = uuid.UUID(node_by_title(validated, N_TRATO)["id"])

    for actor in (learner, second_learner):
        await onboard(actor)
        await enroll(admin, world, actor.user)
        # Same declared profile, so the same `scaffold_band` and the same bucket.
        assert (await actor.post(f"/nodes/{trato}/probe")).status_code == 200

    first = await generate_render(learner, world, trato, ui_format="explanation")
    assert first["status"] == "ready", first
    assert first["cached"] is False

    async with async_session_factory() as db:
        before = (
            await db.execute(select(NodeRender).where(NodeRender.node_id == trato))
        ).scalars().all()
        assert len(before) == 1
        cache_key = before[0].cache_key

    accepted = await second_learner.post(f"/nodes/{trato}/render")
    assert accepted.status_code == 202, accepted.text
    payload = accepted.json()
    # No stream to subscribe to, because there is no work to do.
    assert payload["cached"] is True
    assert payload["request_id"] == ""
    assert payload["render_id"] == first["render_id"]

    served = await second_learner.get(f"/nodes/{trato}/render")
    assert served.status_code == 200, served.text
    assert served.json()["program"] == first["program"]
    assert served.json()["cached"] is True

    async with async_session_factory() as db:
        after = (
            await db.execute(select(NodeRender).where(NodeRender.node_id == trato))
        ).scalars().all()
        assert len(after) == 1, "the cache hit generated a second render anyway"
        assert after[0].cache_key == cache_key
        # Both learners' views are recorded against the one row.
        views = (
            await db.execute(
                select(NodeRenderView).where(NodeRenderView.render_id == after[0].id)
            )
        ).scalars().all()
        assert {view.user_id for view in views} == {
            world.employee.id,
            world.other.id,
        }


# --------------------------------------------------------------------------------- #
# 5. The render stream (§9.2)
# --------------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_the_render_stream_reports_the_pipeline_and_closes_on_ui_done(
    admin: Actor, learner: Actor, world: World
) -> None:
    """The SSE contract B9 codes against: named events, and the stream ends on the
    first terminal one.

    ``run_node_render`` waits up to 0.5 s for a subscriber before starting precisely so
    this handshake is possible: this pub/sub keeps no backlog, so an event published
    before the browser subscribes is lost.
    """
    schema = await propose_and_wait(admin, world)
    validated = await review_all_and_validate(admin, world, schema)
    await _register_probe_fixtures(Path(settings.LLM_FIXTURE_DIR), world.course_id)
    trato = uuid.UUID(node_by_title(validated, N_TRATO)["id"])
    await onboard(learner)
    await enroll(admin, world, world.employee)
    assert (await learner.post(f"/nodes/{trato}/probe")).status_code == 200
    await _register_render_fixtures(
        Path(settings.LLM_FIXTURE_DIR),
        node_id=trato,
        user_id=world.employee.id,
        ui_format="explanation",
    )

    accepted = await learner.post(f"/nodes/{trato}/render")
    assert accepted.status_code == 202, accepted.text
    request_id = accepted.json()["request_id"]
    assert request_id, "a fresh render must hand back a request_id to subscribe to"

    events: list[str] = []
    async with learner.client.stream(
        "GET",
        f"{PREFIX}/nodes/{trato}/render/stream",
        params={"request_id": request_id},
        timeout=30.0,
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        async for line in response.aiter_lines():
            if line.startswith("event: "):
                events.append(line.removeprefix("event: ").strip())
                if events[-1] in ("ui_done", "node_skipped", "error"):
                    break

    assert events, "the stream produced no events"
    assert set(events) <= {
        "render_step",
        "ui_format",
        "ui_block",
        "ui_done",
        "node_skipped",
        "error",
    }
    assert events[-1] == "ui_done", events
    assert "ui_format" in events
    assert "ui_block" in events, "no component was announced as it completed"

    render = await wait_for_render(learner, trato)
    assert render["status"] == "ready"


# --------------------------------------------------------------------------------- #
# 6. The per-node review lock, from the runtime's side
# --------------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_node_added_after_validation_cannot_be_served(
    admin: Actor, learner: Actor, world: World
) -> None:
    """``ensure_node_servable`` closes the "add a node to a validated course" bypass.

    By construction rather than by trust: the runtime checks ``reviewed_at`` on the node
    itself, so a course-level flag cannot vouch for a node no human read.
    """
    schema = await propose_and_wait(admin, world)
    await review_all_and_validate(admin, world, schema)
    await onboard(learner)
    await enroll(admin, world, world.employee)

    async with async_session_factory() as db:
        smuggled = CourseNode(
            org_id=world.org.id,
            course_id=world.course_id,
            title="Nodo colado",
            summary="Anadido sin revision humana.",
            position=99,
            source_document_id=world.document.id,
            source_headings=["Devoluciones"],
        )
        db.add(smuggled)
        await db.commit()
        smuggled_id = smuggled.id

    for call in (
        learner.post(f"/nodes/{smuggled_id}/render"),
        learner.get(f"/nodes/{smuggled_id}/render"),
    ):
        response = await call
        assert response.status_code == 409, response.text
        assert response.json()["field"] == "node_not_reviewed"

    # The unreviewed node is still listed — hiding it would make the block unexplainable.
    listing = (await learner.get(f"/courses/{world.course_id}/nodes")).json()
    assert str(smuggled_id) in {row["id"] for row in listing["nodes"]}


# --------------------------------------------------------------------------------- #
# 7. GDPR: the learner can delete their profile (§3.3)
# --------------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_the_learner_can_delete_the_profile_they_consented_to(
    learner: Actor, world: World
) -> None:
    await onboard(learner)
    assert (await learner.get("/users/me/learner-profile")).status_code == 200

    deleted = await learner.delete("/users/me/learner-profile")
    assert deleted.status_code == 204, deleted.text
    assert (await learner.get("/users/me/learner-profile")).status_code == 404

    async with async_session_factory() as db:
        rows = (
            await db.execute(
                text("SELECT count(*) FROM learner_profiles WHERE user_id = :uid"),
                {"uid": world.employee.id},
            )
        ).scalar_one()
        assert rows == 0


__all__ = ["Actor", "World"]
