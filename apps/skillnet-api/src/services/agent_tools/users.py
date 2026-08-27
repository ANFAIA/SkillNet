"""``users_*`` tools: read the org's people, create a new employee.

Every handler goes through :class:`UserService`/:class:`EnrollmentService` — the
same services the REST routes use — so a tool can never do more than the
equivalent ``POST /users``/``GET /users`` already allows for this admin's
``org_id``.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AppError
from src.models import User
from src.repositories.course_repo import CourseRepository
from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.exercise_repo import ExerciseRepository
from src.repositories.user_repo import UserRepository
from src.schemas.user import UserRead
from src.services.agent_tools.base import ToolSpec
from src.services.enrollment_service import EnrollmentService
from src.services.user_service import UserService


def _user_service(db: AsyncSession) -> UserService:
    return UserService(UserRepository(db))


def _enrollment_service(db: AsyncSession) -> EnrollmentService:
    return EnrollmentService(
        EnrollmentRepository(db), CourseRepository(db), ExerciseRepository(db)
    )


async def _users_list(db: AsyncSession, user: User, args: dict[str, Any]) -> Any:
    rows, total = await _user_service(db).list_users(
        org_id=user.org_id,
        search=args.get("search"),
        role=args.get("role"),
        is_active=args.get("is_active"),
        offset=0,
        limit=min(int(args.get("limit") or 50), 100),
    )
    return {
        "total": total,
        "users": [
            UserRead.model_validate(u).model_dump(mode="json") for u in rows
        ],
    }


async def _users_get_progress(
    db: AsyncSession, user: User, args: dict[str, Any]
) -> Any:
    target_id = args.get("user_id")
    if not target_id:
        raise AppError(message="user_id is required", code="VALIDATION_ERROR", status_code=400)
    users = _user_service(db)
    enrollments_svc = _enrollment_service(db)
    target = await users.get_user(uuid.UUID(str(target_id)), user.org_id)
    enrollments, _total = await enrollments_svc.list_enrollments(
        org_id=user.org_id, user_id=target.id, course_id=None, status=None, offset=0, limit=100
    )
    progress = []
    for enrollment in enrollments:
        fraction = await enrollments_svc.compute_progress(
            enrollment=enrollment, org_id=user.org_id
        )
        progress.append(
            {
                "course_id": str(enrollment.course_id),
                "status": enrollment.status.value,
                "progress": fraction,
                "deadline": enrollment.deadline.isoformat() if enrollment.deadline else None,
            }
        )
    return {
        "user_id": str(target.id),
        "full_name": target.full_name,
        "enrollments": progress,
    }


async def _users_create(db: AsyncSession, user: User, args: dict[str, Any]) -> Any:
    from src.repositories.learner_profile_repo import LearnerProfileRepository

    email = args.get("email")
    full_name = args.get("full_name")
    if not email or not full_name:
        raise AppError(
            message="email and full_name are required",
            code="VALIDATION_ERROR",
            status_code=400,
        )
    created, temporary_password = await _user_service(db).create_employee(
        org_id=user.org_id, email=str(email), full_name=str(full_name)
    )
    # Mirrors `POST /users` (routes/users.py): without this row the onboarding
    # gate silently skips the new employee's first-login setup wizard.
    await LearnerProfileRepository(db).get_or_create(user_id=created.id, org_id=user.org_id)
    await db.commit()
    return {
        "user_id": str(created.id),
        "email": created.email,
        "full_name": created.full_name,
        "temporary_password": temporary_password,
    }


TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="users_list",
        domain="users",
        verb="list",
        description=(
            "List the organization's users (employees/learners). Use this to find "
            "a person by name/email before calling any other users_* or "
            "enrollment_* tool, since those need a user_id."
        ),
        parameters={
            "type": "object",
            "properties": {
                "search": {
                    "type": "string",
                    "description": "Free-text match on name or email.",
                },
                "role": {"type": "string", "enum": ["admin", "employee"]},
                "is_active": {"type": "boolean"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
        },
        handler=_users_list,
    ),
    ToolSpec(
        name="users_get_progress",
        domain="users",
        verb="get_progress",
        description=(
            "Get one user's course enrollments and per-course completion progress "
            "(0.0-1.0). Call users_list first if you only have a name."
        ),
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "UUID from users_list."},
            },
            "required": ["user_id"],
        },
        handler=_users_get_progress,
    ),
    ToolSpec(
        name="users_create",
        domain="users",
        verb="create",
        description=(
            "Create a new employee account with an auto-generated temporary "
            "password (there is no email-invite flow in this deployment — tell "
            "the admin the temporary password so they can pass it on). "
            "WRITE ACTION: only call this after the admin has explicitly "
            "confirmed the email and full name in this conversation."
        ),
        parameters={
            "type": "object",
            "properties": {
                "email": {"type": "string"},
                "full_name": {"type": "string"},
            },
            "required": ["email", "full_name"],
        },
        handler=_users_create,
        requires_confirmation=True,
    ),
)
