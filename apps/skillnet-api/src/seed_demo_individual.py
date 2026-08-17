"""Seed a minimal ``individual`` workspace: one owner, one document, one course.

The public demo (``seed_demo_v2``) seeds a company — five employees, collective
enrollments, an org panel. This seeds the other deployment mode of
``docs/design/audience-modes.md``: a single person who installs SkillNet for
themselves and both administers and learns. So it reuses the very same building
blocks as ``seed_demo_v2`` — no forked content pipeline — but drops everything
collective:

* the organization's ``workspace_mode`` is set to ``individual``;
* the bootstrap admin is the owner (admin who also learns) — no extra users;
* one document and one dynamic course are seeded from the v2 specs;
* no employees and no enrollments (the owner is an admin, who opens courses
  without an enrollment — see ``routes/courses.py``).

Idempotent, like ``seed_demo_v2``. Run after the app has bootstrapped an admin
(``ADMIN_EMAIL``/``ADMIN_PASSWORD``). Setting ``WORKSPACE_MODE=individual`` in
the environment before first boot has the same effect on a fresh deployment;
this script also flips an existing single-org deployment for a local demo.
"""

from __future__ import annotations

from src.core.logging import get_logger
from src.deps.db import async_session_factory, engine
from src.models import Document, WorkspaceMode
from src.seed_demo_v2 import (
    DOCUMENTS,
    DYNAMIC_COURSES,
    _assert_validated,
    _ensure_admin,
    _ensure_dynamic_course,
    _ensure_document,
    _ensure_chunks,
    _ensure_org,
    _ensure_taxonomy,
    _generate_knowledge_packs,
    check_specs,
)

logger = get_logger(__name__)


async def seed(*, refresh: bool = False) -> None:
    check_specs()

    # One document and the one course that is built from it.
    course_spec = DYNAMIC_COURSES[0]
    doc_spec = next(d for d in DOCUMENTS if d.key == course_spec.document_key)

    async with async_session_factory() as session:
        org = await _ensure_org(session)
        # The defining bit: this deployment is a personal workspace.
        org.workspace_mode = WorkspaceMode.INDIVIDUAL
        owner = await _ensure_admin(session, org)
        skills = await _ensure_taxonomy(session, org)

        document: Document = await _ensure_document(session, org, owner, doc_spec)
        chunks = await _ensure_chunks(session, org, document, doc_spec)

        course, nodes = await _ensure_dynamic_course(
            session, org, owner, course_spec, document, skills, refresh=refresh
        )
        await _assert_validated(session, course, nodes)

        # No employees, no enrollments: the owner is the only person, and an admin
        # opens a course without being enrolled.
        await session.commit()
        await _generate_knowledge_packs(org, {course_spec.title: course})

        logger.info(
            "Individual workspace seeded: owner=%s, course=%s (%d nodes), chunks=%d",
            owner.email,
            course_spec.title,
            len(nodes),
            chunks,
        )
        print(  # noqa: T201 - a seed script talks to the operator
            f"\nIndividual workspace ready.\n"
            f"  Owner (admin + learner): {owner.email}\n"
            f"  Course: {course_spec.title} — {len(nodes)} nodes\n"
            f"  workspace_mode = individual\n"
        )

    await engine.dispose()


def main() -> None:
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Seed a minimal individual workspace.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Rewrite the design fields of the existing course from its spec.",
    )
    args = parser.parse_args()
    asyncio.run(seed(refresh=args.refresh))


if __name__ == "__main__":
    main()
