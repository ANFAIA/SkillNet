"""Seed a coherent ``individual`` workspace for end-to-end testing.

The organization/individual split (migration ``0017_workspace_mode``, ``config.py``,
``core/bootstrap.py``, the ``/setup`` flow) already exists and works, but nothing leaves an
``individual`` deployment with example data: a fresh individual org has no course until its
owner generates one by hand. This script fills that gap the same way ``seed_learning_demo``
fills it for the organization demo: it drives the real one-call orchestrator
(:func:`create_course_end_to_end`) so the seeded course is a genuine validated dynamic
course, not a hand-inserted fixture.

Run it inside the API container (it needs the app's DB + LLM config)::

    docker compose exec api uv run python -m src.seed_individual

What it does, idempotently and re-runnably:

1. **Creates (or reuses) one ``individual`` organization** — slug ``individual-demo`` — kept
   entirely separate from the default org, so this never touches ``seed_demo.py`` or
   ``seed_learning_demo.py`` data.
2. **Creates one owner user** who both administers and learns, exactly like a real
   ``/setup`` individual flow: ``role=ADMIN`` plus a completed ``learner_profiles`` row (an
   individual admin does learn — see ``core/bootstrap.py``).
3. **Generates one example course** via :func:`create_course_end_to_end` (schema -> packs ->
   auto-review -> validate -> prewarm). No enrolment step: in an ``individual`` workspace
   there is no assignment concept (``deps/auth.py`` 404s the whole surface), the owner's own
   org membership is what makes the course visible.

Re-running reuses a course already validated with every node's pack ready (same
"reconcile copies" pattern as ``seed_learning_demo``); a partial/broken previous run is
regenerated cleanly instead of accumulating duplicates.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from dataclasses import dataclass

from sqlalchemy import select, text

from src.core.logging import configure_logging, get_logger
from src.deps.db import async_session_factory, engine

from src.models import Course, Organization, User, UserRole, WorkspaceMode
from src.repositories.course_repo import CourseRepository
from src.repositories.learner_profile_repo import LearnerProfileRepository
from src.repositories.learning_event_repo import LearningEventRepository
from src.services.learner_profile_service import LearnerProfileService
from src.services.course_orchestration import (
    CourseEndToEndResult,
    create_course_end_to_end,
)

configure_logging("INFO")
logger = get_logger(__name__)

# --------------------------------------------------------------------------------------
# The individual workspace under test.
# --------------------------------------------------------------------------------------
ORG_SLUG = "individual-demo"
ORG_NAME = "Mi espacio (demo)"

OWNER_EMAIL = "owner@individual.skillnet.dev"
OWNER_PASSWORD = "aprender2026"
OWNER_FULL_NAME = "Owner Demo"

COURSE_TITLE = "Aprender a programar: primeros pasos"
COURSE_DESCRIPTION = (
    "Un curso corto para alguien que nunca ha programado: qué es una variable, un bucle "
    "y una función, con ejemplos que se pueden seguir sin ordenador."
)
COURSE_OUTCOME = "Leer un programa sencillo y explicar qué hace, línea a línea."
COURSE_INTENT_DENSITY = 2  # low: aim for ~4-6 short nodes


# --------------------------------------------------------------------------------------
# Org + owner (idempotent).
# --------------------------------------------------------------------------------------
async def _ensure_individual_org(session) -> Organization:
    org = (
        await session.execute(select(Organization).where(Organization.slug == ORG_SLUG))
    ).scalar_one_or_none()
    if org is not None:
        return org
    org = Organization(name=ORG_NAME, slug=ORG_SLUG, workspace_mode=WorkspaceMode.INDIVIDUAL)
    session.add(org)
    await session.flush()
    return org


async def _ensure_owner(session, org: Organization) -> User:
    user = (
        await session.execute(select(User).where(User.email == OWNER_EMAIL))
    ).scalar_one_or_none()
    if user is None:
        from fastapi_users.password import PasswordHelper

        user = User(
            email=OWNER_EMAIL,
            hashed_password=PasswordHelper().hash(OWNER_PASSWORD),
            org_id=org.id,
            full_name=OWNER_FULL_NAME,
            role=UserRole.ADMIN,
            is_active=True,
            is_superuser=True,
            is_verified=True,
        )
        session.add(user)
        await session.flush()

    # Individual admin == learner: give them a completed profile so onboarding does not
    # fire on every re-run (mirrors the real /setup + first-entry flow).
    repo = LearnerProfileRepository(session)
    service = LearnerProfileService(repo, LearningEventRepository(session))
    profile = await repo.get_by_user(user.id)
    if profile is None or profile.onboarding_completed_at is None:
        await service.complete_onboarding(
            user=user,
            role_title=None,
            sector=None,
            goal=None,
            experience_level="none",
            preset="standard",
            learning_preferences=None,
        )
    await session.flush()
    return user


# --------------------------------------------------------------------------------------
# Course reconciliation — same "keep at most one complete copy" pattern as
# seed_learning_demo, duplicated here rather than imported so this script has no
# dependency on that module (and never risks touching its data).
# --------------------------------------------------------------------------------------
async def _delete_course_ids(session, course_ids: list[uuid.UUID]) -> None:
    if not course_ids:
        return
    params = {"courses": [str(c) for c in course_ids]}
    await session.execute(
        text("DELETE FROM generation_jobs WHERE result_course_id = ANY(:courses)"), params
    )
    await session.execute(
        text("DELETE FROM chat_sessions WHERE course_id = ANY(:courses)"), params
    )
    await session.execute(
        text("DELETE FROM enrollments WHERE course_id = ANY(:courses)"), params
    )
    await session.execute(text("DELETE FROM courses WHERE id = ANY(:courses)"), params)


async def _course_is_complete(session, course_id: uuid.UUID, org_id: uuid.UUID) -> bool:
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


async def _reconcile_course_copies(session, title: str, org_id: uuid.UUID) -> uuid.UUID | None:
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
        keeper = complete[0]
        await _delete_course_ids(session, [c for c in rows if c != keeper])
        await session.commit()
        return keeper
    await _delete_course_ids(session, rows)
    await session.commit()
    return None


@dataclass
class CourseReport:
    reused: bool
    course_id: uuid.UUID | None
    result: CourseEndToEndResult | None = None


async def seed() -> None:
    async with async_session_factory() as db:
        org = await _ensure_individual_org(db)
        await db.commit()
        await db.refresh(org)

    async with async_session_factory() as db:
        org_row = await db.get(Organization, org.id)
        owner = await _ensure_owner(db, org_row)
        await db.commit()
        owner_id = owner.id

    async with async_session_factory() as db:
        keeper = await _reconcile_course_copies(db, COURSE_TITLE, org.id)

    if keeper is not None:
        print(f"  '{COURSE_TITLE}' ya existe completo; se reutiliza ({keeper}).")
        report = CourseReport(reused=True, course_id=keeper)
    else:
        print(f"  Generando '{COURSE_TITLE}' (intent_density={COURSE_INTENT_DENSITY})...")
        result = await create_course_end_to_end(
            COURSE_TITLE,
            org_id=org.id,
            created_by=owner_id,
            intent_density=COURSE_INTENT_DENSITY,
            description=COURSE_DESCRIPTION,
            outcome=COURSE_OUTCOME,
            prewarm=True,
        )
        async with async_session_factory() as db:
            row = (
                await db.execute(
                    select(Course.id)
                    .where(Course.org_id == org.id, Course.title == COURSE_TITLE)
                    .order_by(Course.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        report = CourseReport(reused=False, course_id=row, result=result)
        print(
            f"    -> {result.packs_ready}/{result.node_count} nodos ready, "
            f"validated={result.validated}"
        )

    _report(org, owner, report)
    await engine.dispose()


def _report(org: Organization, owner: User, report: CourseReport) -> None:
    line = "-" * 78
    print()
    print(line)
    print("  SkillNet — demo del modo individual")
    print(line)
    print(f"  Org:       {org.name}  (slug={org.slug}, workspace_mode=individual)")
    print(f"  Owner:     {owner.email}  /  {OWNER_PASSWORD}")
    print()
    if report.reused:
        print(f"  Curso:     {COURSE_TITLE}  [reutilizado]  id={report.course_id}")
    elif report.result is not None:
        print(
            f"  Curso:     {COURSE_TITLE}  {report.result.packs_ready}/"
            f"{report.result.node_count} ready, validated={report.result.validated}  "
            f"id={report.course_id}"
        )
        for w in report.result.warnings:
            print(f"    aviso: {w}")
    else:
        print(f"  Curso:     {COURSE_TITLE}  [sin resultado]")
    print(line)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m src.seed_individual",
        description="Siembra una organización 'individual' de ejemplo. Idempotente.",
    )
    parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # type: ignore[union-attr]
    print()
    print("SkillNet - sembrando el modo individual de ejemplo...")
    asyncio.run(seed())


if __name__ == "__main__":
    main()
