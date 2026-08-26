"""Seed the public SkillNet demo — a self-branded, meta "how we learn" dataset.

This replaces the old bakery-café demo (``seed_demo_v2`` / "La Espiga") as the public,
turnkey demo. Its theme is on-brand: four short, Brilliant-style courses *about how
learning works*, three demo learners with different declared learning styles, and every
course generated + validated + prewarmed at seed time so the demo works the moment it
finishes.

Run it inside the API container (it needs the app's DB + LLM config)::

    docker compose exec api uv run python -m src.seed_learning_demo

What it does, idempotently and re-runnably:

1. **Deletes the old La Espiga runtime data** from the default org (its two dynamic
   courses, the static backup course, the three source documents, and the five
   ``@laespiga.example`` demo employees — with all their nodes, packs, renders,
   enrolments, profiles and events). It never touches the ``admin@skillnet.dev`` account,
   the sponsor org, or any of the other content in the org.

2. **Creates four short courses** via the one-call orchestrator
   (:func:`create_course_end_to_end`): schema → packs (bounded retry on DeepSeek
   flakiness) → auto-review → validate → prewarm. Neutral base tone; the personality is
   applied per-learner through the ``learning_note``.

3. **Creates three demo learners** (personas) with their declared style, and enrols all
   three in all four courses.

4. **Generates media artefacts**: the showcase course gets a podcast AND an infographic
   for every node (so Ana's PodcastPlayer and Bruno's InfographicImage appear inline); the
   other three courses each get one course-level podcast.

It reports honest per-course partial success ("5/6 nodes ready") — a flaky generation
degrades a course, it never aborts the whole seed.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select, text

from src.core.logging import configure_logging, get_logger
from src.deps.db import async_session_factory, engine

# Importing these packages registers the real podcast/infographic generators (they override
# the echo default). Without this a seed process would produce spec-only artefacts with no
# bytes, and the media broker would never offer them in a lesson.
from src.services.media import infographic as _infographic  # noqa: F401
from src.services.media import podcast as _podcast  # noqa: F401

from src.models import (
    Course,
    MediaArtifact,
    MediaKind,
    Organization,
    User,
    UserRole,
)
from src.personalization.learning_note import normalize_learning_note
from src.repositories.course_repo import CourseRepository
from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.exercise_repo import ExerciseRepository
from src.repositories.lesson_progress_repo import LessonProgressRepository
from src.repositories.learner_profile_repo import LearnerProfileRepository
from src.repositories.learning_event_repo import LearningEventRepository
from src.services.enrollment_service import EnrollmentService
from src.services.learner_profile_service import LearnerProfileService
from src.core.exceptions import CapabilityBlockedError
from src.services.media.jobs import enqueue_artifact, spawn_media_job
from src.services.course_orchestration import (
    CourseEndToEndResult,
    create_course_end_to_end,
)

configure_logging("INFO")
logger = get_logger(__name__)

# --------------------------------------------------------------------------------------
# Personas — one shared demo password, on-brand emails.
# --------------------------------------------------------------------------------------
DEMO_PASSWORD = "aprender2026"


@dataclass(frozen=True)
class PersonaSpec:
    email: str
    full_name: str
    #: ``None`` means "no learner_profiles row at all" — the fresh account to show onboarding.
    learning_note: str | None
    #: ``learning_preferences`` v3 bundle; ``None`` for the profile-less fresh learner.
    learning_preferences: dict | None
    role_title: str | None = None
    experience: str | None = None
    note: str = ""


PERSONAS: tuple[PersonaSpec, ...] = (
    PersonaSpec(
        email="ana@skillnet.dev",
        full_name="Ana",
        learning_note="me gustan las metáforas y las analogías",
        # Modality AUDIO -> the media broker offers the PodcastPlayer in her lessons.
        learning_preferences={"version": 3, "modalities": ["audio"]},
        role_title="Persona curiosa",
        experience="some",
        note="Metáforas + AUDIO: ve el podcast (PodcastPlayer) inline.",
    ),
    PersonaSpec(
        email="bruno@skillnet.dev",
        full_name="Bruno",
        learning_note="prefiero las bases y las definiciones primero, con rigor",
        # Modality VISUAL -> the media broker offers the InfographicImage in his lessons.
        learning_preferences={"version": 3, "web_presentation": "visual"},
        role_title="Persona curiosa",
        experience="some",
        note="Definiciones primero + VISUAL: ve la infografía (InfographicImage) inline.",
    ),
    PersonaSpec(
        email="carla@skillnet.dev",
        full_name="Carla",
        learning_note=None,
        learning_preferences=None,
        note="SIN perfil a propósito: la cuenta nueva para mostrar el onboarding.",
    ),
)


# --------------------------------------------------------------------------------------
# Courses — four short, Brilliant-style courses about how learning works.
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class CourseSpec:
    title: str
    description: str
    outcome: str
    intent_density: int = 2  # low: aim for ~4-6 short nodes
    showcase: bool = False


COURSES: tuple[CourseSpec, ...] = (
    CourseSpec(
        title="Cómo aprende tu cerebro",
        description=(
            "Una introducción curiosa a la neurociencia del aprendizaje: cómo se forma la "
            "memoria y por qué estudiar a última hora falla."
        ),
        outcome="Entender cómo tu cerebro fija lo que aprende, y cómo aprovecharlo.",
        intent_density=3,
        showcase=True,
    ),
    CourseSpec(
        title="Sesgos cognitivos",
        description=(
            "Un recorrido por las formas en que la mente se engaña a sí misma, con muchas "
            "situaciones para reconocerlas en ti."
        ),
        outcome="Reconocer los sesgos cognitivos más comunes en tu propio pensamiento.",
        intent_density=2,
    ),
    CourseSpec(
        title="La ciencia de los hábitos",
        description=(
            "Cómo se forman y se rompen los hábitos: el bucle señal-rutina-recompensa y qué "
            "hacer con él."
        ),
        outcome="Comprender el mecanismo de los hábitos para cambiar uno propio.",
        intent_density=2,
    ),
    CourseSpec(
        title="Memoria y olvido",
        description=(
            "La curva del olvido y la repetición espaciada: por qué olvidamos y cómo "
            "recordar durante más tiempo."
        ),
        outcome="Usar la repetición espaciada para retener lo que aprendes.",
        intent_density=2,
    ),
)


@dataclass
class CourseReport:
    spec: CourseSpec
    result: CourseEndToEndResult | None = None
    reused: bool = False
    artifact_ids: list[uuid.UUID] = field(default_factory=list)


# --------------------------------------------------------------------------------------
# Deletion of the old La Espiga data (idempotent).
# --------------------------------------------------------------------------------------
async def _delete_la_espiga(session, org: Organization) -> dict[str, int]:
    """Remove the retired "La Espiga" runtime data from the default org.

    The old bakery-café seed (``seed_demo_v2``) was removed from the codebase, so its
    identifiers are inlined here as literal constants (legacy cleanup for DBs seeded before
    La Espiga was removed — harmless and idempotent on fresh installs, where nothing matches).
    Order respects the NO ACTION foreign keys (enrolments, chat sessions and generation jobs
    must go before the course/user/document they point at); everything else is
    ``ON DELETE CASCADE``. Never touches the admin account or the sponsor org.
    """
    # Legacy La Espiga identifiers (formerly imported from the deleted ``seed_demo_v2``).
    EMAIL_DOMAIN = "laespiga.example"
    course_titles = [
        "Alergenos: informar sin equivocarse",
        "Servicio de sala: de la comanda al cobro",
        "Manejo de caja y arqueo diario (v1 estatico)",
    ]
    doc_titles = [
        "Manual de alergenos e informacion al cliente",
        "Protocolo de sala: de la comanda al cobro",
        "Manejo de caja y arqueo diario",
    ]

    course_ids = list(
        (
            await session.execute(
                select(Course.id).where(
                    Course.org_id == org.id, Course.title.in_(course_titles)
                )
            )
        ).scalars()
    )
    user_ids = list(
        (
            await session.execute(
                select(User.id).where(
                    User.org_id == org.id,
                    User.email.like(f"%@{EMAIL_DOMAIN}"),
                )
            )
        ).scalars()
    )
    doc_ids = list(
        (
            await session.execute(
                text(
                    "SELECT id FROM documents WHERE org_id = :org "
                    "AND title = ANY(:titles)"
                ),
                {"org": str(org.id), "titles": doc_titles},
            )
        ).scalars()
    )

    counts = {
        "courses": len(course_ids),
        "users": len(user_ids),
        "documents": len(doc_ids),
    }
    if not (course_ids or user_ids or doc_ids):
        return counts

    params = {
        "courses": [str(c) for c in course_ids] or [str(uuid.uuid4())],
        "users": [str(u) for u in user_ids] or [str(uuid.uuid4())],
        "docs": [str(d) for d in doc_ids] or [str(uuid.uuid4())],
    }

    # 1. Blocking children (NO ACTION FKs) must be removed first.
    await session.execute(
        text(
            "DELETE FROM generation_jobs WHERE result_course_id = ANY(:courses) "
            "OR source_document_id = ANY(:docs) OR triggered_by = ANY(:users)"
        ),
        params,
    )
    await session.execute(
        text("DELETE FROM chat_sessions WHERE course_id = ANY(:courses)"), params
    )
    await session.execute(
        text("DELETE FROM enrollments WHERE course_id = ANY(:courses)"), params
    )
    # 2. Courses cascade to nodes, renders, packs, media, modules, skills, activities...
    await session.execute(
        text("DELETE FROM courses WHERE id = ANY(:courses)"), params
    )
    # 3. Users cascade to profiles, events, node states, remaining enrolments, tokens...
    await session.execute(text("DELETE FROM users WHERE id = ANY(:users)"), params)
    # 4. Documents cascade to their chunks (their courses are already gone).
    await session.execute(
        text("DELETE FROM documents WHERE id = ANY(:docs)"), params
    )
    await session.commit()
    return counts


async def _delete_course_ids(session, course_ids: list[uuid.UUID]) -> None:
    """FK-safe delete of whole courses (enrolments/chat/jobs first, then the course).

    Everything else — nodes, renders, packs, media, modules, skills, activities — is
    ``ON DELETE CASCADE`` from ``courses``, so this is all that is needed.
    """
    if not course_ids:
        return
    params = {"courses": [str(c) for c in course_ids]}
    await session.execute(
        text("DELETE FROM generation_jobs WHERE result_course_id = ANY(:courses)"),
        params,
    )
    await session.execute(
        text("DELETE FROM chat_sessions WHERE course_id = ANY(:courses)"), params
    )
    await session.execute(
        text("DELETE FROM enrollments WHERE course_id = ANY(:courses)"), params
    )
    await session.execute(text("DELETE FROM courses WHERE id = ANY(:courses)"), params)


async def _course_is_complete(session, course_id: uuid.UUID, org_id: uuid.UUID) -> bool:
    """A course is reusable only if it is validated AND every node has a ready pack.

    This is what makes a re-run *heal* a partially-generated course instead of skipping
    it: a course validated with missing packs (some nodes fall back to the legacy stepper)
    is treated as incomplete and regenerated.
    """
    course = await CourseRepository(session).get_scoped(course_id, org_id)
    if course is None:
        return False
    status = str(getattr(course.schema_status, "value", course.schema_status))
    if status != "validated":
        return False
    node_count = (
        await session.execute(
            text("SELECT count(*) FROM course_nodes WHERE course_id = :c"),
            {"c": str(course_id)},
        )
    ).scalar_one()
    if not node_count:
        return False
    ready = (
        await session.execute(
            text(
                "SELECT count(*) FROM node_knowledge_packs "
                "WHERE course_id = :c AND status = 'ready'"
            ),
            {"c": str(course_id)},
        )
    ).scalar_one()
    return int(ready) >= int(node_count)


async def _reconcile_course_copies(
    session, title: str, org_id: uuid.UUID
) -> uuid.UUID | None:
    """Collapse a title to at most one *complete* copy; return it if it exists.

    Robust against the duplicates that a partial/concurrent previous run can leave: if any
    copy is complete, keep the newest complete one and delete the rest; otherwise delete
    every copy so the caller regenerates cleanly. This is what guarantees a re-run ends
    with exactly one copy per title.
    """
    rows = list(
        (
            await session.execute(
                select(Course.id)
                .where(Course.org_id == org_id, Course.title == title)
                .order_by(Course.created_at.desc())
            )
        ).scalars()
    )
    if not rows:
        return None
    complete = [cid for cid in rows if await _course_is_complete(session, cid, org_id)]
    if complete:
        keeper = complete[0]  # newest complete
        await _delete_course_ids(session, [c for c in rows if c != keeper])
        await session.commit()
        return keeper
    await _delete_course_ids(session, rows)
    await session.commit()
    return None


# --------------------------------------------------------------------------------------
# Personas
# --------------------------------------------------------------------------------------
async def _ensure_persona(session, org: Organization, spec: PersonaSpec) -> User:
    user = (
        await session.execute(select(User).where(User.email == spec.email))
    ).scalar_one_or_none()
    if user is None:
        from fastapi_users.password import PasswordHelper

        user = User(
            email=spec.email,
            hashed_password=PasswordHelper().hash(DEMO_PASSWORD),
            org_id=org.id,
            full_name=spec.full_name,
            role=UserRole.EMPLOYEE,
            is_active=True,
            is_superuser=False,
            is_verified=True,
        )
        session.add(user)
        await session.flush()

    if spec.learning_note is None and spec.learning_preferences is None:
        # The fresh account: no learner_profiles row, so onboarding fires on first login.
        return user

    repo = LearnerProfileRepository(session)
    service = LearnerProfileService(repo, LearningEventRepository(session))
    profile = await repo.get_by_user(user.id)
    if profile is None or profile.onboarding_completed_at is None:
        profile = await service.complete_onboarding(
            user=user,
            role_title=spec.role_title,
            sector=None,
            # No goal: the "Esto te sirve para X" opening line is derived from it, and for a
            # curiosity-driven demo that line is noise on every screen. A null goal makes the
            # frontend omit the line entirely (openingLineFor returns null).
            goal=None,
            experience_level=spec.experience,
            preset="standard",
            learning_preferences=spec.learning_preferences,
        )
    else:
        # Re-run: keep the declared preferences in sync without a full onboarding rewrite.
        from src.personalization.preferences import normalize_learning_preferences

        profile.learning_preferences = normalize_learning_preferences(
            spec.learning_preferences
        ).to_dict()
        profile.goal = None  # drop any legacy goal so the opening line stays hidden
    profile.learning_note = normalize_learning_note(spec.learning_note) or None
    await session.flush()
    return user


async def _enrol_personas(
    session, org: Organization, admin: User, course_ids: list[uuid.UUID],
    user_ids: list[uuid.UUID],
) -> None:
    service = EnrollmentService(
        EnrollmentRepository(session),
        CourseRepository(session),
        ExerciseRepository(session),
        LessonProgressRepository(session),
    )
    for course_id in course_ids:
        try:
            await service.assign(
                org_id=org.id,
                assigned_by=admin.id,
                course_id=course_id,
                user_ids=user_ids,
                deadline=None,
            )
        except Exception as exc:  # noqa: BLE001 - a duplicate enrolment must not abort
            logger.warning("enrol: course %s: %s", course_id, exc)
    await session.commit()


# --------------------------------------------------------------------------------------
# Course-level artefacts for the non-showcase courses
# --------------------------------------------------------------------------------------
async def _enqueue_course_podcast(session, course_id: uuid.UUID, org_id: uuid.UUID) -> uuid.UUID | None:
    course = await CourseRepository(session).get_scoped(course_id, org_id)
    if course is None:
        return None
    try:
        artifact = await enqueue_artifact(
            session, course=course, node=None, kind=MediaKind.PODCAST, spec={"scope": "course"}
        )
    except CapabilityBlockedError as exc:
        # The demo is meant to seed anywhere, including a deployment with no voice key.
        # Skipping the podcast leaves the courses intact; failing here would leave a
        # half-seeded database over an optional extra.
        logger.info("Skipping the course podcast: %s", exc.message)
        return None
    await session.commit()
    spawn_media_job(artifact.id)
    return artifact.id


# --------------------------------------------------------------------------------------
# Wait for artefacts (bounded)
# --------------------------------------------------------------------------------------
async def _wait_for_artifacts(artifact_ids: list[uuid.UUID], timeout_s: float = 1200.0) -> dict[str, int]:
    import time

    if not artifact_ids:
        return {"done": 0, "error": 0, "pending": 0}
    deadline = time.monotonic() + timeout_s
    ids = [str(a) for a in artifact_ids]
    while time.monotonic() < deadline:
        async with async_session_factory() as db:
            rows = (
                await db.execute(
                    select(MediaArtifact.status).where(
                        MediaArtifact.id.in_(artifact_ids)
                    )
                )
            ).scalars().all()
        statuses = [str(getattr(s, "value", s)) for s in rows]
        done = sum(1 for s in statuses if s == "done")
        error = sum(1 for s in statuses if s == "error")
        pending = len(ids) - done - error
        if pending == 0:
            return {"done": done, "error": error, "pending": 0}
        await asyncio.sleep(4.0)
    async with async_session_factory() as db:
        rows = (
            await db.execute(
                select(MediaArtifact.status).where(MediaArtifact.id.in_(artifact_ids))
            )
        ).scalars().all()
    statuses = [str(getattr(s, "value", s)) for s in rows]
    done = sum(1 for s in statuses if s == "done")
    error = sum(1 for s in statuses if s == "error")
    return {"done": done, "error": error, "pending": len(ids) - done - error}


# --------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------
async def _resolve_identity() -> tuple[Organization, User]:
    async with async_session_factory() as db:
        org = (
            await db.execute(
                select(Organization).where(Organization.slug == "default").limit(1)
            )
        ).scalar_one_or_none()
        if org is None:
            org = (await db.execute(select(Organization).limit(1))).scalar_one_or_none()
        if org is None:
            raise SystemExit("No organization found. Boot the app once, then re-run.")
        admin = (
            await db.execute(
                select(User)
                .where(User.org_id == org.id, User.role == UserRole.ADMIN)
                .order_by(User.created_at)
                .limit(1)
            )
        ).scalar_one_or_none()
        if admin is None:
            raise SystemExit("No admin user found in the organization.")
        return org, admin


# --------------------------------------------------------------------------- #
# Per-persona episode pre-render
# --------------------------------------------------------------------------- #
_PERSONA_PREWARM_NODES = 2
_PERSONA_PREWARM_ATTEMPTS = 4
_PERSONA_RENDER_TIMEOUT_S = 150.0


async def _render_until_ready(
    user_id: uuid.UUID, node_id: uuid.UUID, course_id: uuid.UUID
) -> str:
    """Force a personalized render and retry until it lands READY (a real episode).

    Adaptive-episode generation is stochastic: a fresh attempt sometimes emits a malformed
    Table or a hallucinated component and the render degrades to a flat fallback. For a
    turnkey demo we don't want a persona's *cached* first lesson to be that fallback, so we
    force a render and, on a fallback, drop the row (freeing the learner's ``cache_key``) and
    try again a bounded number of times. The key carries the learner's learning-note
    fingerprint, so this warms exactly the row their normal open will cache-hit and pin.
    """
    from src.models import Course, CourseNode, NodeRender, User
    from src.services.node_render_service import NodeRenderService

    for _attempt in range(_PERSONA_PREWARM_ATTEMPTS):
        # Free the learner's base cache_key so the forced render writes to it, not a salt.
        async with async_session_factory() as db:
            await db.execute(
                text("DELETE FROM node_renders WHERE node_id = :n AND generated_by = :u"),
                {"n": node_id, "u": user_id},
            )
            await db.commit()
        async with async_session_factory() as db:
            user = await db.get(User, user_id)
            node = await db.get(CourseNode, node_id)
            course = await db.get(Course, course_id)
            if user is None or node is None or course is None:
                return "missing"
            await NodeRenderService(db).request_render(
                user=user, node=node, course=course, force=True
            )
            await db.commit()
        deadline = time.monotonic() + _PERSONA_RENDER_TIMEOUT_S
        while time.monotonic() < deadline:
            await asyncio.sleep(3.0)
            async with async_session_factory() as db:
                status = (
                    await db.execute(
                        select(NodeRender.status)
                        .where(
                            NodeRender.node_id == node_id,
                            NodeRender.generated_by == user_id,
                        )
                        .order_by(NodeRender.created_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
            if status is None:
                continue
            value = str(getattr(status, "value", status))
            if value == "ready":
                return "ready"
            if value in {"fallback", "failed"}:
                break  # a fresh attempt clears most stochastic DSL slips
    return "fallback"


async def _leading_nodes(course_id: uuid.UUID, node_count: int) -> list[uuid.UUID]:
    from src.repositories.course_node_repo import CourseNodeRepository

    async with async_session_factory() as db:
        nodes = list(
            await CourseNodeRepository(db).list_for_course(course_id, include_archived=False)
        )
    return [n.id for n in nodes if n.reviewed_at is not None][:node_count]


async def _prewarm_persona_episodes(
    persona_ids: list[uuid.UUID], course_counts: list[tuple[uuid.UUID, int]]
) -> dict[str, int]:
    """Warm the first node(s) of EVERY demo course, per persona, until they render clean.

    ``course_counts`` pairs each course with how many leading nodes to warm (the showcase
    gets an instant start *and* one continuation; the other courses get an instant start).

    Two things make this land on the row a persona's normal open will cache-hit:

    * ``_render_until_ready`` forces the render on the persona's BASE ``cache_key`` (it deletes
      any existing per-user row first, so the force never salts), and that key carries the
      persona's learning-note *and* media-offer fingerprints.
    * This MUST run only after the courses' media artefacts are ``done``. The media-offer
      fingerprint is empty while an artefact is still generating, so warming earlier would key
      the render differently from the open-time key (podcast/infographic now ready) and the
      persona would cache-miss and wait — the exact bug this seeding step exists to prevent.
    """
    summary: dict[str, int] = {}
    for course_id, node_count in course_counts:
        leading = await _leading_nodes(course_id, node_count)
        for user_id in persona_ids:
            for node_id in leading:
                outcome = await _render_until_ready(user_id, node_id, course_id)
                summary[outcome] = summary.get(outcome, 0) + 1
    return summary


async def seed(*, skip_delete: bool = False) -> None:
    org, admin = await _resolve_identity()
    org_id, admin_id = org.id, admin.id

    # 1. Delete the old La Espiga data.
    if not skip_delete:
        async with async_session_factory() as db:
            org_row = await db.get(Organization, org_id)
            deleted = await _delete_la_espiga(db, org_row)
        print(
            f"  La Espiga eliminada: {deleted['courses']} cursos, "
            f"{deleted['users']} usuarios, {deleted['documents']} documentos."
        )
    else:
        deleted = {"courses": 0, "users": 0, "documents": 0}

    # 2. Personas (create/refresh profiles) before enrolment and warming.
    persona_ids: list[uuid.UUID] = []
    async with async_session_factory() as db:
        org_row = await db.get(Organization, org_id)
        for spec in PERSONAS:
            user = await _ensure_persona(db, org_row, spec)
            persona_ids.append(user.id)
        await db.commit()

    # 3. Create the four courses via the one-call orchestrator.
    reports: list[CourseReport] = []
    for spec in COURSES:
        # Idempotency + de-duplication: collapse any existing copies of this title to at
        # most one *complete* one (validated with every node's pack ready). If a complete
        # copy survives, reuse it; otherwise all copies are gone and we regenerate.
        async with async_session_factory() as db:
            keeper = await _reconcile_course_copies(db, spec.title, org_id)
        if keeper is not None:
            print(f"  [{spec.title}] ya existe completo; se reutiliza ({keeper}).")
            reports.append(CourseReport(spec=spec, reused=True))
            continue

        artifacts = ["podcast", "infographic"] if spec.showcase else None
        print(f"  Generando '{spec.title}' (intent_density={spec.intent_density})...")
        result = await create_course_end_to_end(
            spec.title,
            org_id=org_id,
            created_by=admin_id,
            intent_density=spec.intent_density,
            description=spec.description,
            outcome=spec.outcome,
            generate_artifacts=artifacts,
            artifact_node_limit=12 if spec.showcase else 1,
            prewarm=True,
        )
        report = CourseReport(spec=spec, result=result)
        report.artifact_ids = [
            uuid.UUID(a["artifact_id"]) for a in result.artifacts
        ]
        reports.append(report)
        print(
            f"    -> {result.packs_ready}/{result.node_count} nodos ready, "
            f"validated={result.validated}, artefactos={len(result.artifacts)}"
        )

    # 4. Resolve the final course ids and enrol the personas in all of them.
    async with async_session_factory() as db:
        title_to_id: dict[str, uuid.UUID] = {}
        for spec in COURSES:
            row = (
                await db.execute(
                    select(Course.id).where(
                        Course.org_id == org_id, Course.title == spec.title
                    ).order_by(Course.created_at.desc()).limit(1)
                )
            ).scalar_one_or_none()
            if row is not None:
                title_to_id[spec.title] = row
    course_ids = list(title_to_id.values())

    async with async_session_factory() as db:
        admin_row = await db.get(User, admin_id)
        org_row = await db.get(Organization, org_id)
        await _enrol_personas(db, org_row, admin_row, course_ids, persona_ids)

    # 5. Course-level podcast for the three non-showcase courses.
    for spec in COURSES:
        if spec.showcase:
            continue
        cid = title_to_id.get(spec.title)
        if cid is None:
            continue
        async with async_session_factory() as db:
            art_id = await _enqueue_course_podcast(db, cid, org_id)
        if art_id is not None:
            for r in reports:
                if r.spec.title == spec.title:
                    r.artifact_ids.append(art_id)

    # 7. Wait for every artefact to reach a terminal state.
    all_artifacts = [a for r in reports for a in r.artifact_ids]
    print(f"  Esperando {len(all_artifacts)} artefactos multimedia...")
    art_summary = await _wait_for_artifacts(all_artifacts)
    print(
        f"  Artefactos: {art_summary['done']} done, {art_summary['error']} error, "
        f"{art_summary['pending']} pendientes."
    )

    # 8. Per-persona pre-render of the FIRST lesson of EVERY demo course, run *after* the
    #    media artefacts are done so the warmed row is keyed with the same media-offer
    #    fingerprint the persona's normal open computes (else they cache-miss and wait).
    #    The showcase gets an instant start plus one continuation; the rest, an instant start.
    if persona_ids and title_to_id:
        course_counts: list[tuple[uuid.UUID, int]] = []
        for spec in COURSES:
            cid = title_to_id.get(spec.title)
            if cid is None:
                continue
            course_counts.append((cid, _PERSONA_PREWARM_NODES if spec.showcase else 1))
        print(
            f"  Pre-renderizando la primera lección de {len(course_counts)} cursos "
            f"para {len(persona_ids)} personas..."
        )
        warm = await _prewarm_persona_episodes(persona_ids, course_counts)
        print(
            f"    -> episodios listos: {warm.get('ready', 0)}, "
            f"fallback: {warm.get('fallback', 0)}, faltantes: {warm.get('missing', 0)}"
        )

    _report(org, admin, deleted, reports, title_to_id, art_summary)
    await engine.dispose()


def _report(org, admin, deleted, reports, title_to_id, art_summary) -> None:
    line = "-" * 78
    print()
    print(line)
    print("  SkillNet — demo pública: cómo aprendemos")
    print(line)
    print(f"  Admin:     {admin.email}")
    print(f"  Personas:  contraseña única -> {DEMO_PASSWORD}")
    for spec in PERSONAS:
        print(f"    - {spec.email}  ({spec.note})")
    print()
    print(f"  La Espiga eliminada: {deleted}")
    print()
    print("  Cursos:")
    for r in reports:
        cid = title_to_id.get(r.spec.title)
        if r.reused:
            print(f"    - {r.spec.title}  [reutilizado]  id={cid}")
        elif r.result is not None:
            print(
                f"    - {r.spec.title}  {r.result.packs_ready}/{r.result.node_count} ready, "
                f"validated={r.result.validated}, artefactos={len(r.artifact_ids)}  id={cid}"
            )
            for w in r.result.warnings:
                print(f"        aviso: {w}")
        else:
            print(f"    - {r.spec.title}  [sin resultado]")
    print()
    print(f"  Artefactos multimedia: {art_summary}")
    print(line)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m src.seed_learning_demo",
        description="Siembra la demo pública 'cómo aprendemos'. Idempotente.",
    )
    parser.add_argument(
        "--skip-delete",
        action="store_true",
        help="No borrar los datos de La Espiga (solo crear/actualizar la demo nueva).",
    )
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # type: ignore[union-attr]
    print()
    print("SkillNet - sembrando la demo pública 'cómo aprendemos'...")
    asyncio.run(seed(skip_delete=args.skip_delete))


if __name__ == "__main__":
    main()
