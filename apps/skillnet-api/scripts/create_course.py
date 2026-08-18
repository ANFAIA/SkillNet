#!/usr/bin/env python3
"""Create a dynamic course end to end in ONE command.

Wraps :func:`src.services.course_orchestration.create_course_end_to_end` so an
operator or a subagent can build a fully-validated course with a single call,
instead of the seven-step API dance.

Run it inside the API container (it needs the app's DB + LLM config):

    docker compose exec -T api sh -c \\
        'cd /app && uv run python scripts/create_course.py "Food safety basics"'

    # ground on a document, enrol a learner, generate a podcast:
    docker compose exec -T api sh -c 'cd /app && uv run python scripts/create_course.py \\
        "Onboarding" --document-id <uuid> --enroll-user-id <uuid> --artifacts podcast'

By default it runs as the bootstrap admin of the first organization; override with
--org-id / --admin-id.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid

from sqlalchemy import select

from src.deps.db import async_session_factory
from src.models import Organization, User, UserRole
from src.services.course_orchestration import create_course_end_to_end


async def _resolve_identity(
    org_id: str | None, admin_id: str | None
) -> tuple[uuid.UUID, uuid.UUID]:
    """Resolve (org_id, admin_id), defaulting to the first org and its admin."""
    async with async_session_factory() as db:
        if org_id:
            org_uuid = uuid.UUID(org_id)
        else:
            org = (await db.execute(select(Organization).limit(1))).scalar_one_or_none()
            if org is None:
                raise SystemExit("No organization found. Boot the app first.")
            org_uuid = org.id
        if admin_id:
            admin_uuid = uuid.UUID(admin_id)
        else:
            admin = (
                await db.execute(
                    select(User)
                    .where(User.org_id == org_uuid, User.role == UserRole.ADMIN)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if admin is None:
                raise SystemExit("No admin user found in the organization.")
            admin_uuid = admin.id
    return org_uuid, admin_uuid


async def _run(args: argparse.Namespace) -> int:
    org_uuid, admin_uuid = await _resolve_identity(args.org_id, args.admin_id)
    print(
        f"Creating course '{args.title}' as admin {admin_uuid} in org {org_uuid}...",
        file=sys.stderr,
    )
    result = await create_course_end_to_end(
        args.title,
        org_id=org_uuid,
        created_by=admin_uuid,
        document_id=uuid.UUID(args.document_id) if args.document_id else None,
        intent_density=args.intent_density,
        enroll_user_id=uuid.UUID(args.enroll_user_id) if args.enroll_user_id else None,
        generate_artifacts=args.artifacts or None,
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    # Exit non-zero if the course did not validate, so scripts can detect failure.
    return 0 if result.validated else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("title", help="Course title / topic to build")
    parser.add_argument("--document-id", default=None, help="Ground on a ready document (UUID)")
    parser.add_argument(
        "--intent-density", type=int, default=3, help="Depth 1-5 (default 3)"
    )
    parser.add_argument("--enroll-user-id", default=None, help="Employee to enrol (UUID)")
    parser.add_argument(
        "--artifacts",
        nargs="*",
        default=None,
        help="Media kinds for the first node, e.g. --artifacts podcast infographic",
    )
    parser.add_argument("--org-id", default=None, help="Override organization (UUID)")
    parser.add_argument("--admin-id", default=None, help="Override creating admin (UUID)")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
